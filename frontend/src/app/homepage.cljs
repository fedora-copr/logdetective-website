(ns app.homepage
  (:require [reagent.core :as r]
            [clojure.string :as str]
            [cljs.source-map.base64 :as base64 :refer [encode]]
            [cljs.core.match :refer-macros [match]]
            [app.homepage-validation :refer [validate]]))


(def input-values (r/atom nil))
(def input-errors (r/atom []))
(def current-hash-atom (r/atom nil))


(defn current-hash []
  (. (. js/document -location) -hash))

(defn homepage-submit []
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
      (set! (.-href (.-location js/window)) url))))

(defn on-tab-click [href]
  (reset! current-hash-atom href)
  (reset! input-errors []))

(defn on-input-change [target]
  (swap! input-values assoc
         (keyword (.-name target))
         (.-value target)))

(defn render-navigation-item [title href]
  (let [active? (= href @current-hash-atom)]
    [:li {:class "nav-item ml-auto"}
     [:a {:class ["nav-link" (if active? "active" nil)]
          :href href
          :on-click #(on-tab-click href)}
      title]]))

(defn render-navigation []
   [:div {:class "card-header"}
    [:ul {:class "nav nav-tabs card-header-tabs"}
     (render-navigation-item "Copr" "#copr")
     (render-navigation-item "Koji" "#koji")
     (render-navigation-item "Packit" "#packit")
     (render-navigation-item "URL" "#url")
     (render-navigation-item "Container" "#container")]])

(defn render-card [provider url title img text inputs]
  [:div {:class "card-body"}
   [:div {:class "row"}
    [:div {:class "col-2"}
     [:a {:href url :title (if provider (str "Go to " provider) nil)}
      [:img {:src img, :class "card-img-top", :alt "..."}]]]

    [:div {:class "col-8"}
     [:h2 {:class "card-title"} title]
     [:p {:class "card-text"} text]

     (for [[i input] (map-indexed vector inputs)]
       ^{:key i}
       [:div {:class "input-group mb-3 container"}
        input
        (when (= (- (count inputs) 1) i)
          [:button
           {:class "btn btn-outline-primary",
            :type "button", :id "button-addon2"
            :on-click #(homepage-submit)}
           "Let's go"])])]

    [:div {:class "col-2"}]]])

(defn input [name placeholder]
  [:input
   {:type "text"
    :class ["form-control"
            (when (some #{name} @input-errors)
              "validation-error")]
    :name name
    :placeholder placeholder
    :value (get @input-values (keyword name))
    :on-change #(on-input-change (.-target %))}])

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
   "Specify a Koji build ID to fetch and display all relevant logs."
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
         "#container" (render-container-card)
         :else        (render-copr-card)))

(defn homepage []
  (reset! current-hash-atom
          (if (str/blank? (current-hash)) "#copr" (current-hash)))
  [:div {:class "card text-center"}
   (render-navigation)
   (render-cards)])
