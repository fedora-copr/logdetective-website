(ns app.three-column-layout.core
  (:require
   [app.helpers :refer [fontawesome-icon]]
   [app.components.jumbotron :refer [loading-icon]]))

(defn three-column-layout [left middle right panel]
  [:div {:class "row"}
   [:div {:class "col-3" :id "left-column"} left]
   [:div {:class "col-6" :id "middle-column"} panel middle]
   [:div {:class "col-3" :id "right-column"} right]])

(defn instructions-item [done? text]
  (let [class (if done? "done" "todo")
        icon-name (if done? "fa-square-check" "fa-square")]
    [:li {:class class}
     [:span {:class "fa-li"}
      (fontawesome-icon icon-name)]
     text]))

(defn instructions [items]
  [:<>
   [:h4 {} "Instructions"]
   [:ul {:class "fa-ul"}
    (into [:<>] items)]])

(defn display-error-middle-top [error-title error-description]
  (when error-description
    [:div
     [:div {:class "alert alert-danger alert-dismissible fade show text-center"}
      [:strong error-title]
      [:p error-description]
      [:button {:type "button" :class "btn-close" :data-bs-dismiss "alert"}]]]))

(defn notify-being-uploaded [status]
  (when (= status "submitting")
    [:h2 {:class "lead text-body-secondary"}
     (loading-icon)
     "  Uploading ..."]))

(defn status-panel [status error-title error-description]
  (or
   (notify-being-uploaded status)
   (display-error-middle-top error-title error-description)))
