(ns app.contribute.events
  (:require
   [clojure.set :refer [rename-keys]]
   [lambdaisland.fetch :as fetch]
   [app.helpers :refer
    [current-path
     remove-trailing-slash]]
   [app.editor.core :refer [active-file]]
   [app.components.snippets :refer [snippets]]
   [app.contribute.logic :refer [file-id]]
   [app.contribute.atoms :refer
    [backend-data
     spec
     container
     ok-status]]
   [app.common.state :refer
    [status
     error-title
     error-description
     fail-reason
     how-to-fix]]))

(defn submit-form
  "Render annotation submission form with retrieved logs"
  []
  (let [url (remove-trailing-slash (str "/frontend" (current-path)))
        ;; Clojure typically uses dashes instead of underscores in keyword
        ;; names. However, this is going to be dumped as JSON and we expect
        ;; underscores there
        body {:fail_reason @fail-reason
              :how_to_fix @how-to-fix
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

                       (= (:status data) "ok") ((reset! status "submitted")
                                                (reset! ok-status data))
                       :else nil))))))

(defn on-how-to-fix-textarea-change [target]
  (reset! how-to-fix (.-value target)))

(defn on-change-fail-reason [event]
  (let [target (.-target event)
        value (.-value target)]
    (reset! fail-reason value)))

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
