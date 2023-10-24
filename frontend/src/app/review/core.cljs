(ns app.review.core
 (:require
  [reagent.core :as r]
  [html-entities :as html-entities]
  [lambdaisland.fetch :as fetch]
  [app.helpers :refer [current-path]]
  [app.editor.core :refer [editor]]
  [app.components.accordion :refer [accordion]]
   [app.components.jumbotron :refer
    [render-jumbotron
     render-error
     loading-screen]]
  [app.three-column-layout.core :refer
   [three-column-layout
    instructions-item
    instructions]]))


(def files (r/atom nil))
(def error-description (r/atom nil))
(def error-title (r/atom nil))


(defn init-data-review []
  (let [url (str "/frontend" (current-path))]
    (-> (fetch/get url {:accept :json :content-type :json})
        (.then (fn [resp]
                 (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data]
                 (if (:error data)
                   (do
                     (reset! error-title (:error data))
                     (reset! error-description (:description data)))
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
   [(instructions-item
     true
     "We fetched a random sample from our collected data set")

    (instructions-item
     nil
     "Go through all snippets and either upvote or downvote them")

    (instructions-item
     nil
     "Is the explanation why did the build fail correct?")

    (instructions-item
     nil
     "Is the explanation how to fix the issue correct?")

    (instructions-item nil "Submit")]))

(defn middle-column []
  (editor @files))

(defn buttons []
  [[:button {:type "button"
             :class "btn btn-outline-primary"
             :on-click nil}
    "+1"]
   [:button {:type "button"
             :class "btn btn-outline-danger"
             :on-click nil}
    "-1"]])

(defn snippet [text]
  {:title "Snippet"
   :body [:p {} text]
   :buttons (buttons)})

(defn card [title text]
  [:div {:class "card"}
   [:div {:class "card-body"}
       [:h5 {:class "card-title"} title]
    [:p {:class "card-text"} text]
    (into [:<>] (buttons))]])

(defn right-column []
  [:<>
   [:br]
   [:br]

   ;; TODO When clicking any of the accordion items, the snippet should display
   ;; in the middle column log file. That will be the only currently highlighted
   ;; snippet, so that it is easily understandable.
   (accordion
    "ID"
    [(snippet "This is the annotation for the first snippet")
     (snippet "And this is for the second snippet")])

   [:br]
   (card
    "Why did the build fail?"
    "Here is some explanation why the build failed")

   [:br]
   (card
    "How to fix the issue?"
    "Here is some explanation how to fix the issue")

   [:div {}
    [:label {:class "form-label"} "Ready to submit the results?"]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click nil}
     "Submit"]]])

(defn review []
  (cond
    @error-description
    (render-error @error-title @error-description)

    true
    ;; @files
    (three-column-layout
     (left-column)
     (middle-column)
     (right-column))

    :else
    (loading-screen "Please wait, fetching logs from our dataset.")))
