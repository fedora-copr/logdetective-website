(ns app.homepage
  (:require [reagent.core :as r]
            [clojure.string :as str]
            [cljs.core.match :refer-macros [match]]))


(def current-hash-atom (r/atom nil))


(defn current-hash []
  (. (. js/document -location) -hash))

(defn render-navigation-item [title href]
  (let [active? (= href @current-hash-atom)]
    [:li {:class "nav-item ml-auto"}
     [:a {:class ["nav-link" (if active? "active" nil)]
          :href href
          :on-click #(reset! current-hash-atom href)}
      title]]))

(defn render-navigation []
   [:div {:class "card-header"}
    [:ul {:class "nav nav-tabs card-header-tabs"}
     (render-navigation-item "Copr" "#copr")
     (render-navigation-item "Koji" "#koji")
     (render-navigation-item "Packit" "#packit")
     (render-navigation-item "URL" "#url")]])

(defn render-card [title img text placeholder]
  [:div {:class "card-body"}
   [:img {:src img, :class "card-img-top", :alt "..."}]
   [:h4 {:class "card-title"} title]
   [:p {:class "card-text"} text]
   [:div {:class "input-group mb-3 container"}
    [:input
     {:type "text",
      :class "form-control",
      :placeholder placeholder}]
    [:button
     {:class "btn btn-outline-secondary",
      :type "button", :id "button-addon2"}
     "Let's go"]]])

(defn render-copr-card []
  (render-card
   "Submit logs from Copr"
   "img/copr-logo.png"
   "Specify a Copr build ID and we will fetch and display all relevant logs."
   "Copr build ID, e.g. 6302362"))

(defn render-packit-card []
  (render-card
   "Submit logs from Packit"
   "img/packit-logo.png"
   (str/join "" ["Specify a Packit job ID, we will match it to a build, "
                 "fetch, and display all relevant logs."])
   "Packit job ID, e.g. TODO"))

(defn render-koji-card []
  (render-card
   "Submit logs from Koji"
   "img/koji-logo.png"
   "Specify a Koji task ID or build ID to fetch and display all relevant logs."
   "Koji task ID, e.g. 6302362"))

(defn render-url-card []
  (render-card
   "Submit logs from URL"
   "img/url-icon.png"
   (str/join "" ["Paste an URL to a log file, or a build in some build system. "
                 "If recognized, we will fetch and display all relevant logs."])
   "TODO"))

(defn render-cards []
  (match @current-hash-atom
         "#copr"   (render-copr-card)
         "#packit" (render-packit-card)
         "#koji"   (render-koji-card)
         "#url"    (render-url-card)
         :else     (render-copr-card)))

(defn homepage []
  (reset! current-hash-atom
          (if (str/blank? (current-hash)) "#copr" (current-hash)))
  [:div {:class "card text-center"}
   (render-navigation)
   (render-cards)])
