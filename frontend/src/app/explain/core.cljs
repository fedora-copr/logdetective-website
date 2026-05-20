(ns app.explain.core
  (:require
   [clojure.string :as str]
   [cljs.core.match :refer-macros [match]]
   [ajax.core :refer [POST]]
   [app.helpers :refer [current-path redirect query-params-get]]
   [app.homepage-validation :refer [validate]]
   [app.common.provider-forms :as pf]
   [app.explain.atoms :as atoms]
   [app.components.jumbotron :refer [render-error loading-screen]]
   [app.common.state :refer
    [status
     error-description
     error-title
     handle-backend-error]]
   [app.prompt.core :as prompt]))

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
  [:div {:id "content" :class "container"}
   [:section
    {:class "py-1 text-center container"}
    [:div
     {:class "row py-lg-3"}
     [:div
      {:class "col-md-10 mx-auto"}
      [:h1 {:class "fw-light"} "Log Detective"]
      [:p
       {:class "lead text-body-secondary"}
       @prompt/mission-statement-prompt]
      (prompt/disclaimer)
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
      (reset! prompt/form data))))

(defn provider-path []
  (let [path (current-path)]
    (when (not= path "/explain")
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
        (prompt/send query-url)
        (loading-screen "Getting a response from the server"))

      ;; Provider path: e.g. /explain/copr/123/fedora-39-x86_64
      (and ppath (not= @status "ok"))
      (do
        (send-provider (str "/frontend/explain/" ppath))
        (loading-screen "Getting a response from the server"))

      @prompt/form
      (prompt/two-column-layout)

      :else
      (explain-input))))

(defn init-explain []
  (reset! status nil)
  (reset! prompt/form nil))
