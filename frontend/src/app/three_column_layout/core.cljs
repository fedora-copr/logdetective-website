(ns app.three-column-layout.core
 (:require
  [app.helpers :refer [fontawesome-icon]]))


(defn three-column-layout [left middle right]
  [:div {:class "row"}
   [:div {:class "col-3" :id "left-column"} left]
   [:div {:class "col-6" :id "middle-column"} middle]
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
