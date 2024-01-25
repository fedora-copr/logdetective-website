(ns app.components.jumbotron
  (:require
   [app.helpers :refer [fontawesome-icon]]))

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

(defn loading-screen [title]
  (render-jumbotron
   "loading"
   "Loading"
   title
   "..."
   [:div {:class "spinner-border", :role "status"}
    [:span {:class "sr-only"} "Loading..."]]))

(defn render-succeeded []
  (render-jumbotron
   "succeeded"
   "Thank you!"
   "Successfully submitted, thank you for your contribution."
   "..."
   [:a {:type "submit"
        :class "btn btn-primary btn-lg"
        :href "/"}
    [:<> (fontawesome-icon "fa-plus") " Add another log"]]))
