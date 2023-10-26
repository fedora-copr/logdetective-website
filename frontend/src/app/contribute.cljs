(ns app.contribute
  (:require
   [reagent.core :as r]
   [clojure.string :as str]
   [cljs.core.match :refer-macros [match]]
   [lambdaisland.fetch :as fetch]
   [web.Range :refer [surround-contents]]
   ["html-entities" :as html-entities]
   [app.helpers :refer
    [current-path
     fontawesome-icon
     remove-trailing-slash]]
   [app.three-column-layout.core :refer
    [three-column-layout
     instructions-item
     instructions]]
   [app.editor.core :refer [editor]]
   [app.components.jumbotron :refer
    [render-jumbotron
     render-error
     loading-screen
     render-succeeded]]
   [app.components.accordion :refer [accordion]]
   [app.contribute-atoms :refer
    [how-to-fix
     fail-reason
     status
     snippets
     files
     spec
     error-description
     error-title
     backend-data
     log
     fas
     build-id
     build-id-title
     build-url]]
   [app.contribute-events :refer
    [submit-form
     add-snippet
     on-snippet-textarea-change
     on-how-to-fix-textarea-change
     on-change-fas
     on-change-fail-reason
     on-accordion-item-show
     on-click-delete-snippet]]))


(defn fetch-logs []
  (let [url (remove-trailing-slash (str "/frontend" (current-path)))]
    (-> (fetch/get url {:accept :json :content-type :json})
        (.then (fn [resp]
                 (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data]
                 (if (:error data)
                   (do
                     (reset! error-title (:error data))
                     (reset! error-description (:description data)))
                   (do
                     (reset! backend-data data)
                     (reset! log (:content (:log data)))
                     (reset! build-id (:build_id data))
                     (reset! build-id-title (:build_id_title data))
                     (reset! build-url (:build_url data))
                     (reset! spec (:spec_file data))

                     (reset!
                      files
                      (vec (map (fn [log]
                                  ;; We must html encode all HTML characters
                                  ;; because we are going to render the log
                                  ;; files dangerously
                                  (update log :content #(.encode html-entities %)))
                                (:logs data))))

                     (reset! error-title nil)
                     (reset! error-description nil))))))))

(defn init-data []
  (fetch-logs))

(defn left-column []
  (instructions
   [(instructions-item
     (not-empty @files)

     (if (= @build-id-title "URL")
       [:<>
        (str "We fetched logs from ")
        [:a {:href @build-url} "this URL"]]

       [:<>
        (str "We fetched logs for " @build-id-title " ")
        [:a {:href @build-url} (str "#" @build-id)]]))

    ;; Maybe "Write why do you think the build failed"

    (instructions-item
     (not-empty @snippets)
     "Find log snippets relevant to the failure")

    (instructions-item
     (not-empty @snippets)
     "Anotate snippets by selecting them, and clicking 'Anotate selection'")

    (instructions-item
     (not-empty (:comment (first @snippets)))
     "Describe what makes the snippets interesting")

    (instructions-item
     (not-empty @how-to-fix)
     "Describe how to fix the issue")

    (instructions-item nil "Submit")]))

(defn middle-column []
  (editor @files))

(defn accordion-snippet [snippet]
  (when snippet
    {:title "Snippet"
     :body
     [:textarea
      {:class "form-control"
       :rows "3"
       :placeholder "What makes this snippet relevant?"
       :on-change #(on-snippet-textarea-change %)}]
     :buttons
     [[:button {:type "button"
                :class "btn btn-outline-danger"
                :on-click #(on-click-delete-snippet %)}
       "Delete"]]}))

(defn right-column []
  [:<>
   [:div {}
    [:label {:class "form-label"} "Your FAS username:"]
    [:input {:type "text"
             :class "form-control"
             :placeholder "Optional - Your FAS username"
             :on-change #(on-change-fas %)}]]

   [:label {:class "form-label"} "Interesting snippets:"]
   (when (not-empty @snippets)
     [:div {}
      [:button {:class "btn btn-secondary btn-lg" :on-click #(add-snippet)} "Add"]
      [:br]
      [:br]])

   (accordion
    "accordionItems"
    (vec (map (fn [snippet] (accordion-snippet snippet)) @snippets)))

   (when (empty? @snippets)
     [:div {:class "card" :id "no-snippets"}
      [:div {:class "card-body"}
       [:h5 {:class "card-title"} "No snippets yet"]
       [:p {:class "card-text"}
        (str "Please select interesting parts of the log files and press the "
             "'Add' button to annotate them")]
       [:button {:class "btn btn-secondary btn-lg"
                 :on-click #(add-snippet)}
        "Add"]]])

   [:div {}
    [:label {:class "form-label"} "Why did the build fail?"]
    [:textarea {:class "form-control" :rows 3
                :placeholder "Please describe what caused the build to fail."
                :on-change #(on-change-fail-reason %)}]]

   [:div {}
    [:label {:class "form-label"} "How to fix the issue?"]
    [:textarea {:class "form-control" :rows 3
                :placeholder (str "Please describe how to fix the issue in "
                                  "order for the build to succeed.")
                :on-change #(on-how-to-fix-textarea-change (.-target %))}]]

   [:div {}
    [:label {:class "form-label"} "Ready to submit the results?"]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click #(submit-form)}
     "Submit"]]])

(defn contribute []
  ;; I don't know why we need to do it this way,
  ;; instead of like :on-click is done
  ;; (js/document.addEventListener "selectionchange" on-selection-change)

  (cond
    @error-description
    (render-error @error-title @error-description)

    (= @status "submitting")
    (loading-screen "Please wait, submitting results.")

    (= @status "submitted")
    (render-succeeded)

    @files
    (do
      (when (not-empty @snippets)
        (let [accordion (.getElementById js/document "accordionItems")]
          (.addEventListener accordion "show.bs.collapse" on-accordion-item-show)))

      (three-column-layout
       (left-column)
       (middle-column)
       (right-column)))

    :else
    (loading-screen "Please wait, fetching logs from the outside world.")))
