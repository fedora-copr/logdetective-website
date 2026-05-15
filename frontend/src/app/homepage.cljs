(ns app.homepage
  (:require [reagent.core :as r]
            [clojure.string :as str]
            [cljs.core.match :refer-macros [match]]
            [app.homepage-validation :refer [validate]]
            [lambdaisland.fetch :as fetch]
            [app.components.jumbotron :refer [render-error]]
            [app.common.provider-forms :as pf]
            [app.helpers :refer
             [current-path
              redirect
              local-storage-enabled
              local-storage-error
              remove-trailing-slash
              upload-error]]))

(def current-hash (r/atom (. (. js/document -location) -hash)))

(def input-values (r/atom nil))
(def input-errors (r/atom []))
(def backend-stats (r/atom nil))
(def current-hash-atom (r/atom (or (and (not (str/blank? @current-hash)) @current-hash) "#copr")))
(def error (r/atom nil))

(defn fetch-stats-backend []
  (let [url (remove-trailing-slash (str "/stats" (current-path)))]
    (-> (fetch/get url {:accept :json :content-type :json})
        (.then (fn [resp]
                 (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [resp]
                 (reset! backend-stats resp))))))

(defn on-submit [event]
  (.preventDefault event)
  (validate current-hash-atom input-values input-errors)
  (let [source (str/replace @current-hash-atom "#" "")
        params (match @current-hash-atom
                 "#copr"      [(get @input-values :copr-build-id)
                               (get @input-values :copr-chroot)]
                 "#packit"    [(get @input-values :packit-id)]
                 "#koji"      [(get @input-values :koji-build-id)
                               (get @input-values :koji-arch)]
                 "#url"       [(js/btoa (get @input-values :url))]
                 "#container" [(js/btoa (get @input-values :url))])
        url (str/join "/" (concat ["/contribute" source] (map str/trim params)))]
    (when (empty? @input-errors)
      (redirect url))))

(defn on-submit-upload [event]
  (.preventDefault event)
  (if-not (local-storage-enabled)
    (reset! error (local-storage-error))
    (do
      (.setItem js/localStorage "name" (get @input-values :name))
      (try
        (.setItem js/localStorage "content" (get @input-values :file))
        (catch js/Error e
          (reset! error (upload-error (str e)))))
      (validate current-hash-atom input-values input-errors)
      (when (and (empty? @input-errors) (nil? @error))
        (set! (.-href (.-location js/window)) "/contribute/upload")))))

(defn on-tab-click [href]
  (reset! current-hash-atom href)
  (reset! input-errors []))

(defn on-input-change [target]
  (pf/on-input-change-handler target input-values))

(defn on-input-change-file [event]
  (let [target (.-target event)
        path (-> target .-value)
        name (last (str/split path #"\\"))
        reader (js/FileReader.)
        set-atom (fn [e]
                   (swap! input-values assoc :name name)
                   (swap! input-values assoc
                          (keyword (.-name target))
                          (-> e .-target .-result)))
        file (first (array-seq (.. event -target -files)))]
    (.addEventListener reader "load" set-atom)
    (.readAsText reader file)))

(def contribute-tabs
  [["Copr" "#copr"]
   ["Koji" "#koji"]
   ["Packit" "#packit"]
   ["URL" "#url"]
   ["Upload" "#upload"]
   ["Container" "#container"]])

(defn render-navigation []
  (pf/render-navigation contribute-tabs current-hash-atom on-tab-click))

(defn render-stats []
  (when @backend-stats
    [:<>
    [:div {:id "collected-logs-counter"}
      [:p "You and others have contributed " (:total_reports @backend-stats) " annotated logs"]]]))

(defn render-card [provider url title img text inputs]
  (if (= provider "Upload")
    (pf/render-card provider url title img text inputs #'on-submit-upload)
    (pf/render-card provider url title img text inputs #'on-submit)))

(defn input [name placeholder]
  (pf/input-field name placeholder input-values input-errors pf/on-input-change-handler))

(defn input-file [name]
  [:input
   {:type "file"
    :class ["form-control"
            (when (some #{name} @input-errors)
              "validation-error")]
    :name name
    :on-change #(on-input-change-file %)}])

(defn render-copr-card []
  (render-card
   "Copr"
   "https://copr.fedorainfracloud.org"
   "Submit logs from Copr"
   "img/copr-logo.png"
   "Specify a Copr build ID and we will fetch and display all relevant logs."
   [(input "copr-build-id" "Copr build ID, e.g. 6302362")
    (input "copr-chroot" "Chroot name, e.g. fedora-39-x86_64 or srpm-builds")]))

(defn render-packit-card []
  (render-card
   "Packit"
   "https://dashboard.packit.dev"
   "Submit logs from Packit"
   "img/packit-logo.png"
   (str/join "" ["Specify a Packit job ID, we will match it to a build, "
                 "fetch, and display all relevant logs."])
   [(input "packit-id" "Packit job ID, e.g. 1015788")]))

(defn render-koji-card []
  (render-card
   "Koji"
   "https://koji.fedoraproject.org"
   "Submit logs from Koji"
   "img/koji-logo.png"
   "Specify a Koji build ID or task ID with method=buildArch to fetch and display all relevant logs."
   [(input "koji-build-id" "Koji build ID, e.g. 2274591")
    (input "koji-arch" "Architecture, e.g. x86_64")]))

(defn render-url-card []
  (render-card
   nil
   nil
   "Submit RPM logs from URL"
   "img/url-icon.png"
   (str/join "" ["Paste an URL to a log file, or a build in some build system. "
                 "If recognized, we will fetch and display all relevant logs."])
   [(input "url" "https://paste.centos.org/view/raw/5ba21754")]))

(defn render-upload-card []
  (render-card
   "Upload"
   nil
   "Upload RPM logs from your computer"
   "img/upload-icon.png"
   (str
    "Upload a RPM log file from your computer. "
    "Files larger than several MB are not supported.")
   [(input-file "file")]))

(defn render-container-card []
  (render-card
   nil
   nil
   "Submit container logs from URL"
   "img/url-icon.png"
   "Paste an URL to a raw container log file."
   [(input "url" "https://paste.centos.org/view/raw/5ba21754")]))

(defn render-cards []
  (match @current-hash-atom
    "#copr"      (render-copr-card)
    "#packit"    (render-packit-card)
    "#koji"      (render-koji-card)
    "#url"       (render-url-card)
    "#upload"    (render-upload-card)
    "#container" (render-container-card)
    :else        (render-copr-card)))

(defn homepage []
  (if @error
    (render-error (:title @error) (:description @error))
    [:div {:class "card text-center"}
     (render-stats)
     (render-navigation)
     (render-cards)]))
