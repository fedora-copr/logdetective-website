(ns app.components.jumbotron
 (:require
  [reagent.core :as r]))


(defn render-jumbotron [id h1 title description icon]
  [:div {:id id :class "py-5 text-center container rounded"}
   [:h1 h1]
   [:p {:class "lead text-body-secondary"} title]
   [:p {:class "text-body-secondary"} description]
   icon])

(defn render-error [title description]
  (render-jumbotron
   "error"
   "Oops!"
   title
   description
   [:i {:class "fa-solid fa-bug"}]))

(defn loading-screen []
  (render-jumbotron
   "loading"
   "Loading"
   "Please wait, fetching logs from the outside world."
   "..."
   [:div {:class "spinner-border", :role "status"}
    [:span {:class "sr-only"} "Loading..."]]))
