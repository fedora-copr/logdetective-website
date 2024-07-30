(ns app.components.accordion)

(defn accordion-item [i item show?]
  [:div {:class "accordion-item" :key i}
   [:h2 {:class "accordion-header"}
    [:button
     {:class "accordion-button"
      :type "button"
      :data-bs-toggle "collapse"
      :data-bs-target (str "#itemCollapse" i)
      :aria-controls (str "itemCollapse" i)}
     [:<> (:title item) " " (inc i)]]]

   [:div {:id (str "itemCollapse" i)
          :class ["accordion-collapse collapse" (if show? "show" nil)]
          :data-bs-parent "#accordionItems"
          :data-index-number i}

    [:div {:class "accordion-body"
           :data-index-number i}
     (:body item)
     [:div {:class "accordion-buttons"
            :data-index-number i}
      [:div {:class "btn-group"}
       (into [:<>] (:buttons item))]]]]])

(defn accordion-items [items]
  (doall (for [enumerated-item (map-indexed list items)
               :let [i (first enumerated-item)
                     item (second enumerated-item)
                     show? (= i (- (count items) 1))]
               :when item]
           (accordion-item i item show?))))

(defn accordion [id items]
  (when items
    [:div {:class "accordion" :id id}
     (accordion-items items)]))
