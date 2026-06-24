(ns app.explain.core
  (:require
   [clojure.string :as str]
   [malli.core :as m]
   [cljs.core.match :refer-macros [match]]
   [ajax.core :refer [POST]]
   [app.helpers :refer [current-path redirect query-params-get change-url]]
   [app.validation :refer [validate]]
   [app.common.provider-forms :as pf]
   [app.explain.atoms :as atoms]
   [app.components.jumbotron :refer [render-error loading-screen]]
   [app.common.state :refer
    [status
     error-description
     error-title
     handle-backend-error]]))

(def InputSchema
  [:map {:closed true}
   [:explanation :string]

   [:extracted_snippets
    [:vector
     [:map
      [:snippet :string]
      [:source_file :string]
      [:line_number :int]]]]

   [:logs
    [:vector
     [:map
      [:name :string]
      [:content :string]]]]])

;; TODO We allow nil for easier debugging now but should reject it later
(def OutputSchema
  [:map {:closed true}
   [:prompt [:maybe :string]]])

(defn send [url]
  (let [data {:prompt url}]
    (if (m/validate OutputSchema data)
      (do
        (change-url (str "?url=" url))
        (reset! status "waiting")
        (POST "/frontend/explain/"
          :params data
          :format :json
          :response-format :json
          :keywords? true

          :error-handler
          (fn [error]
            (handle-backend-error
             (:error (:response error))
             (:description (:response error))))

          :handler
          (fn [data]
            (if (m/validate InputSchema data)
              (do
                (reset! status "ok")
                (reset! atoms/form data))
              (handle-backend-error
               "Invalid data"
               "Got invalid data from the backend. This is likely a bug.")))))

      (if (not url)
        (reset! status "No URL provided. Please enter a URL.")
        (handle-backend-error
         "Client error"
         "Something went wrong when preparing a request to server")))))

(defn left-column []
  [:div {:class "col-6", :id "left-column"}
   [:h2 "Explanation"]
   (map (fn [x] [:p x])
        (-> @atoms/form :explanation (str/split #"\n")))
   [:p @atoms/ai-gen-disclaimer]])

(defn reason [id snippet source_file line_number]
  (let [accordion-id "#accordionExample"
        heading-id (str "heading-reason-" id)
        collapse-id (str "collapse-reason-" id)]
    [:div {:class "accordion-item" :key id}
     [:h2 {:class "accordion-header" :id heading-id}
      [:button
       {:class "accordion-button collapsed"
        :type "button",
        :data-bs-toggle "collapse"
        :data-bs-target (str "#" collapse-id)
        :aria-expanded "false"
        :aria-controls collapse-id}
        [:span
          {:class "source-file"}
          source_file
          ] " : "
        [:span
          {:class "line-number"}
          line_number] " | "
        [:span
          {:class "truncated-snippet"}
          snippet]]]

      [:div
        {
          :id collapse-id
          :class "accordion-collapse collapse"
          :aria-labelledby heading-id
          :data-bs-parent accordion-id}
        [:div
          [:code {:class "full-snippet"} snippet]]
        ]
      ]))

(defn download-log [log]
  (let [a (.createElement js/document "a")
        blob (new js/Blob #js [(:content log)] #js {:type "text/plain"})
        url (.createObjectURL js/URL blob)]
    (.setAttribute a "href" url)
    (.setAttribute a "download" (:name log))
    (.click a)))

(defn right-column []
  [:div {:class "col-6", :id "right-column"}
   [:div {:class "float-end"}
    (for [log (:logs @atoms/form)]
      ^{:key (:name log)}
      [:button {:type "button"
                :class "btn btn-outline-primary ms-1"
                :on-click #(download-log log)}
       [:i {:class "fa-solid fa-floppy-disk"}]
       (str " " (:name log))])]

   [:h2 "Extracted snippets"]
   [:div {:class "accordion accordion-flush" :id "accordionExample"}
    (map-indexed
     (fn [i x] (reason i (:snippet x) (:source_file x) (:line_number x)))
     (:extracted_snippets @atoms/form))]])

(defn two-column-layout []
  [:div {:class "row" :id "content-main"}
   (left-column)
   (right-column)])

(defn disclaimer []
  [:div {:class "alert alert-warning text-left" :role "alert"}
   [:p "The service is experimental and subject to limitations:"]
   [:ol
    [:li "Response time can run into minutes, if multiple requests arrive simultaneously."]
    [:li "We use a general-purpose model that may not have the most recent information."]
    [:li "The service may be unstable. Please report any issues you may encounter."]]
   [:p "You are about to use a tool that utilizes AI technology to analyze your build failure log."]
   [:p "Submitted information will not be stored. Ready to submit the results to the AI tool for analysis?"]])

;; --- Input mode: provider selection tabs ---

(def explain-tabs
  [["Copr" "#copr"]
   ["Koji" "#koji"]
   ["Packit" "#packit"]
   ["OBS" "#obs"]
   ["URL" "#url"]
   ["Container" "#container"]])

(defn on-tab-click [href]
  (reset! atoms/current-hash-atom href)
  (reset! atoms/input-errors []))

(defn on-submit [event]
  (.preventDefault event)
  (validate atoms/current-hash-atom atoms/input-values atoms/input-errors)
  (let [source (str/replace @atoms/current-hash-atom "#" "")
        params (match @atoms/current-hash-atom
                 "#copr"      [(get @atoms/input-values :copr-build-id)
                               (get @atoms/input-values :copr-chroot)]
                 "#packit"    [(get @atoms/input-values :packit-id)]
                 "#koji"      [(get @atoms/input-values :koji-build-id)
                               (get @atoms/input-values :koji-arch)]
                 "#obs"       [(get @atoms/input-values :obs-project)
                               (get @atoms/input-values :obs-repository)
                               (get @atoms/input-values :obs-architecture)
                               (get @atoms/input-values :obs-package)]
                 "#url"       [(js/btoa (get @atoms/input-values :url))]
                 "#container" [(js/btoa (get @atoms/input-values :url))])
        url (str/join "/" (concat ["/explain" source] (map str/trim params)))]
    (when (empty? @atoms/input-errors)
      (redirect url))))

(defn input [name placeholder]
  (pf/input-field name placeholder atoms/input-values atoms/input-errors pf/on-input-change-handler))

(defn render-copr-card []
  (pf/render-card
   "Copr"
   "https://copr.fedorainfracloud.org"
   "Explain logs from Copr"
   "img/copr-logo.png"
   "Specify a Copr build ID and we will fetch, analyze, and explain all relevant logs."
   [(input "copr-build-id" "Copr build ID, e.g. 6302362")
    (input "copr-chroot" "Chroot name, e.g. fedora-39-x86_64 or srpm-builds")]
   #'on-submit))

(defn render-packit-card []
  (pf/render-card
   "Packit"
   "https://dashboard.packit.dev"
   "Explain logs from Packit"
   "img/packit-logo.png"
   "Specify a Packit job ID, we will match it to a build, fetch, and explain all relevant logs."
   [(input "packit-id" "Packit job ID, e.g. 1015788")]
   #'on-submit))

(defn render-koji-card []
  (pf/render-card
   "Koji"
   "https://koji.fedoraproject.org"
   "Explain logs from Koji"
   "img/koji-logo.png"
   "Specify a Koji build ID or task ID to fetch and explain all relevant logs."
   [(input "koji-build-id" "Koji build ID, e.g. 2274591")
    (input "koji-arch" "Architecture, e.g. x86_64")]
   #'on-submit))

(defn render-obs-card []
  (pf/render-card
   "OBS"
   "https://build.opensuse.org"
   "Explain logs from Open Build Service"
   "img/opensuse-logo.png"
   (str/join "" ["Specify an OBS project, repository, architecture, and "
                 "package; we will fetch and explain the build log."])
   [(input "obs-project" "Project, e.g. openSUSE:Factory")
    (input "obs-repository" "Repository, e.g. standard")
    (input "obs-architecture" "Architecture, e.g. x86_64")
    (input "obs-package" "Package, e.g. ed")]
   #'on-submit))

(defn render-url-card []
  (pf/render-card
   nil
   nil
   "Explain RPM logs from URL"
   "img/url-icon.png"
   "Paste a URL to a log file. We will fetch and explain it."
   [(input "url" "https://paste.centos.org/view/raw/5ba21754")]
   #'on-submit))

(defn render-container-card []
  (pf/render-card
   nil
   nil
   "Explain container logs from URL"
   "img/url-icon.png"
   "Paste a URL to a raw container log file."
   [(input "url" "https://paste.centos.org/view/raw/5ba21754")]
   #'on-submit))

(defn render-cards []
  (match @atoms/current-hash-atom
    "#copr"      (render-copr-card)
    "#packit"    (render-packit-card)
    "#koji"      (render-koji-card)
    "#obs"       (render-obs-card)
    "#url"       (render-url-card)
    "#container" (render-container-card)
    :else        (render-copr-card)))

(defn explain-input []
  [:div {:class "container provider-form"}
   [:section
    {:class "py-1 text-center container"}
    [:div
     {:class "row py-lg-3"}
     [:div
      {:class "col-md-10 mx-auto"}
      [:h1 {:class "fw-light"} "Log Detective"]
      [:p
       {:class "lead text-body-secondary"}
       @atoms/mission-statement-prompt]
      (disclaimer)
      [:div {:class "py-4"}
       [:div {:class "card text-center"}
        (pf/render-navigation explain-tabs atoms/current-hash-atom on-tab-click)
        (render-cards)]]]]]])

;; --- Results mode: analyze via provider path ---

(defn send-provider [api-url]
  (reset! status "waiting")
  (POST api-url
    :format :json
    :response-format :json
    :keywords? true

    :error-handler
    (fn [error]
      (handle-backend-error
       (:error (:response error))
       (:description (:response error))))

    :handler
    (fn [data]
      (reset! status "ok")
      (reset! atoms/form data))))

(defn provider-path []
  (let [path (current-path)]
    (when (and (not= path "/explain") (not= path "/"))
      (str/replace path #"^/explain/" ""))))

;; --- Main component ---

(defn explain-page []
  (let [query-url (query-params-get "url")
        ppath (provider-path)]
    (cond
      (= @status "error")
      (render-error @error-title @error-description)

      (= @status "waiting")
      (loading-screen "Getting a response from the server")

      ;; Old ?url= flow: backward compatible
      (and query-url (not= @status "ok"))
      (do
        (send query-url)
        (loading-screen "Getting a response from the server"))

      ;; Provider path: e.g. /explain/copr/123/fedora-39-x86_64
      (and ppath (not= @status "ok"))
      (do
        (send-provider (str "/frontend/explain/" ppath))
        (loading-screen "Getting a response from the server"))

      @atoms/form
      (two-column-layout)

      :else
      (explain-input))))

(defn init-explain []
  (reset! status nil)
  (reset! atoms/form nil))
