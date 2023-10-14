(ns app.review.core
 (:require
  [reagent.core :as r]
  [html-entities :as html-entities]
  [lambdaisland.fetch :as fetch]
  [app.helpers :refer [current-path]]
  [app.editor.core :refer [editor]]
  [app.three-column-layout.core :refer
   [three-column-layout
    instructions-item
    instructions]]))


(def files (r/atom nil))


(defn init-data-review []
  (let [url (str "/frontend" (current-path))]
    (-> (fetch/get url {:accept :json :content-type :json})
        (.then (fn [resp]
                 (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data]
                 (if (:error data)
                   (do
                     (js/console.log (:error data))
                     (js/console.log (:description data)))
                   (do
                     (reset!
                      files
                      (vec (map (fn [log]
                                  ;; We must html encode all HTML characters
                                  ;; because we are going to render the log
                                  ;; files dangerously
                                  (update log :content #(.encode html-entities %)))
                                (:logs data)))))))))))

(defn left-column []
  (instructions
   [(instructions-item nil "TODO 1")
    (instructions-item nil "TODO 2")
    (instructions-item nil "Submit")]))

(defn middle-column []
  (editor @files))

(defn right-column []
  [:h2 {} "TODO"])

(defn review []
  (three-column-layout
   (left-column)
   (middle-column)
   (right-column)))
