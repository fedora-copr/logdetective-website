(ns app.components.jumbotron)

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

(defn loading-icon []
  [:div {:class "spinner-border", :role "status"}
   [:span {:class "sr-only"} "Loading..."]])

(defn loading-screen [title]
  (render-jumbotron
   "loading"
   "Loading"
   title
   "..."
   (loading-icon)))
