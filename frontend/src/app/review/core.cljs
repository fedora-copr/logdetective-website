(ns app.review.core
 (:require
  [reagent.core :as r]
  [html-entities :as html-entities]
  [lambdaisland.fetch :as fetch]
  [app.helpers :refer [current-path]]
  [app.editor.core :refer [editor]]
  [app.components.accordion :refer [accordion]]
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


(defn snippet [text]
  {:title "Snippet"
   :body
   [:textarea
    {:class "form-control"
     :rows "3"
     :placeholder text
     :on-change nil}]
   :buttons
   [[:button {:type "button"
              :class "btn btn-outline-primary"
              :on-click nil}
       "+1"]
    [:button {:type "button"
              :class "btn btn-outline-danger"
              :on-click nil}
       "-1"]]})

(defn right-column []
  [:<>
   [:h2 {} "TODO"]
   (accordion
    "ID"
    [(snippet "TEXT 1")
     (snippet "TEXT 2")])])

(defn review []
  (three-column-layout
   (left-column)
   (middle-column)
   (right-column)))
