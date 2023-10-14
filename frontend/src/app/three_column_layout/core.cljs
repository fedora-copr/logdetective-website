(ns app.three-column-layout.core)


(defn three-column-layout [left middle right]
  [:div {:class "row"}
   [:div {:class "col-3" :id "left-column"} left]
   [:div {:class "col-6" :id "middle-column"} middle]
   [:div {:class "col-3" :id "right-column"} right]])
