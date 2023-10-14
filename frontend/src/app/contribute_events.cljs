(ns app.contribute-events
  (:require
   [reagent.core :as r]
   [lambdaisland.fetch :as fetch]
   [app.helpers :refer
    [current-path]]
   [app.contribute-logic :refer
    [file-id
     clear-selection
     selection-node-id
     highlight-current-snippet]]
   [app.contribute-atoms :refer
    [how-to-fix
     snippets
     active-file
     files]]))


(defn submit-form []
  (let [url (str "/frontend" (current-path))
        body {:how-to-fix @how-to-fix
              :snippets @snippets}]
    (-> (fetch/post url {:accept :json :content-type :json :body body})
        (.then (fn [resp] (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data] data)))))

(defn add-snippet []
  (when (= (selection-node-id) "log")
    (highlight-current-snippet)

    ;; Save the log with highlights, so they are remembered when switching
    ;; between file tabs
    (let [log (.-innerHTML (.getElementById js/document "log"))]
      (reset! files (assoc-in @files [@active-file :content] log)))

    (let [snippet
          {:text (.toString (.getSelection js/window))
           :comment nil
           :file (:name (get @files @active-file))}]
      (swap! snippets conj snippet))
    (clear-selection)))

;; For some reason, compiler complains it cannot infer type of the `event`
;; variable, so I am specifying it as a workaround
(defn on-accordion-item-show [^js/Event event]
  (let [snippet-id (int (.-indexNumber (.-dataset (.-target event))))
        snippet (nth @snippets snippet-id)
        file-name (:file snippet)]
  (reset! active-file (file-id file-name))))

;; We might need this function for enabling/disabling the "new snippet" button
;; based on whether user selected something (within the <pre>log</pre> area)
;; (defn on-selection-change [event]
;;   (let [selection (js/window.getSelection)]
;;     (js/console.log selection)
;;     (js/console.log selection.anchorOffset)
;;     (js/console.log selection.focusOffset)))

(defn on-click-delete-snippet [^js/Event event]
  (let [snippet-id (int (.-indexNumber (.-dataset (.-target event))))]
    ;; We don't want to remove the element entirely because we want to preserve
    ;; snippet numbers that follows
    (swap! snippets assoc snippet-id nil)

    ;; Remove the highlight
    (let [span (.getElementById js/document (str "snippet-" snippet-id))
          text (.-innerHTML span)]
      (.replaceWith span text))))
