(ns app.review.events
  (:require
   [app.editor.core :refer [active-file]]
   [app.components.snippets :refer [snippets]]
   [app.review.logic :refer [index-of-file]]
   [app.review.atoms :refer [votes form]]))

(defn on-accordion-item-show [^js/Event event]
  (let [snippet-id (int (.-indexNumber (.-dataset (.-target event))))
        snippet (nth @snippets snippet-id)
        file-name (:file snippet)]
    (reset! active-file (index-of-file file-name))))

(defn vote [key value]
  (reset! votes (assoc @votes key value)))

(defn on-vote-button-click [key value]
  (let [current-value (key @votes)
        value (if (= value current-value) 0 value)]
    (vote key value)))

(defn on-change-form-input [event]
  (let [target (.-target event)
        key (keyword (.-name target))
        value (.-value target)]
    (reset! form (assoc @form key value))))
