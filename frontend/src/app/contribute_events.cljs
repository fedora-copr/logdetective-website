(ns app.contribute-events
  (:require
   [clojure.set :refer [rename-keys]]
   [lambdaisland.fetch :as fetch]
   [app.helpers :refer
    [current-path
     remove-trailing-slash
     previous-siblings
     local-storage-enabled]]
   [app.editor.core :refer [active-file]]
   [app.contribute-logic :refer
    [file-id
     clear-selection
     selection-node-id
     selection-contains-snippets?
     highlight-current-snippet]]
   [app.contribute-atoms :refer
    [how-to-fix
     error-title
     backend-data
     error-description
     fail-reason
     status
     snippets
     fas
     spec
     container
     files]]))

(defn submit-form []
  (let [url (remove-trailing-slash (str "/frontend" (current-path)))
        ;; Clojure typically uses dashes instead of underscores in keyword
        ;; names. However, this is going to be dumped as JSON and we expect
        ;; underscores there
        body {:fail_reason @fail-reason
              :how_to_fix @how-to-fix
              :username (if @fas (str "FAS:" @fas) nil)
              :logs
              (map (fn [file]
                     {:name (:name file)
                      :content (:content file)
                      :snippets
                      (map (fn [snippet]
                             (-> snippet
                                 (rename-keys {:comment :user_comment
                                               :start-index :start_index
                                               :end-index :end_index})
                                 (dissoc :file)))
                            ;; Only snippets for this file
                           (filter
                            (fn [snippet]
                              (= (:file snippet) (:name file)))
                            @snippets))})
                   ;; We can't use @files here because they contain highlight
                   ;; spans, HTML escaping, etc.
                   (:logs @backend-data))
              :spec_file @spec
              :container_file @container}]

    ;; Remember the username, so we can prefill it the next time
    (when (and @fas (local-storage-enabled))
      (.setItem js/localStorage "fas" @fas))

    (reset! status "submitting")
    (-> (fetch/post url {:accept :json :content-type :json :body body})
        (.then (fn [resp] (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data]
                 (cond (:error data)
                       (do
                         (reset! error-title (:error data))
                         (reset! error-description (:description data))
                         ;; go back to "has files" state, let users fix
                         ;; validation errors
                         (reset! status nil))

                       (= (:status data) "ok")
                       (reset! status "submitted")

                       :else nil))))))

(defn add-snippet []
  (when (and (= (selection-node-id) "log")
             (not (selection-contains-snippets?)))
    (highlight-current-snippet)

    ;; Save the log with highlights, so they are remembered when switching
    ;; between file tabs
    (let [log (.-innerHTML (.getElementById js/document "log"))]
      (reset! files (assoc-in @files [@active-file :content] log)))

    (let [selection (.getSelection js/window)
          content (.toString selection)

          ;; The position is calculated from the end of the last node
          ;; This can be be either a previous snippet span or if the text
          ;; longer than 65536 characters than it is implictily split into
          ;; multiple sibling text nodes
          start (.-anchorOffset selection)

          ;; Calculate the real starting index from the beginning of the log
          offset (->> selection
                      .-anchorNode
                      previous-siblings
                      (map #(.-textContent %))
                      (map #(count %))
                      (reduce +))
          start (+ start offset)

          ;; Index of the last snippet character. When parsing in python, don't
          ;; forget to do text[start:end+1]
          end (+ start (count content) -1)

          snippet
          {:text content
           :start-index start
           :end-index end
           :comment nil
           :file (:name (get @files @active-file))}]
      (swap! snippets conj snippet))
    (clear-selection)))

(defn on-how-to-fix-textarea-change [target]
  (reset! how-to-fix (.-value target)))

(defn on-change-fas [event]
  (let [target (.-target event)
        value (.-value target)]
    (reset! fas value)))

(defn on-change-fail-reason [event]
  (let [target (.-target event)
        value (.-value target)]
    (reset! fail-reason value)))

;; For some reason, compiler complains it cannot infer type of the `target`
;; variable, so I am specifying it as a workaround
(defn on-snippet-textarea-change [^js/Event event]
  (let [target (.-target event)
        index (int (.-indexNumber (.-dataset (.-parentElement target))))
        value (.-value target)]
    (reset! snippets (assoc-in @snippets [index :comment] value))))

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
  (let [target (.-target event)
        snippet-id (int (.-indexNumber (.-dataset (.-parentElement target))))]
    ;; We don't want to remove the element entirely because we want to preserve
    ;; snippet numbers that follows
    (swap! snippets assoc snippet-id nil)

    ;; Remove the highlight
    (let [span (.getElementById js/document (str "snippet-" snippet-id))
          text (.-innerHTML span)]
      (.replaceWith span text))))
