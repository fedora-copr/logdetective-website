(ns app.contribute
  (:require
   [reagent.core :as r]
   [clojure.string :as str]
   [cljs.core.match :refer-macros [match]]
   [lambdaisland.fetch :as fetch]
   [web.Range :refer [surround-contents]]
   ["html-entities" :as html-entities]
   [app.helpers :refer [current-path fontawesome-icon]]
   [app.three-column-layout.core :refer
    [three-column-layout
     instructions-item
     instructions]]
   [app.editor.core :refer [editor]]
   [app.contribute-atoms :refer
    [how-to-fix
     snippets
     files
     error-description
     error-title
     backend-data
     log
     build-id
     build-id-title
     build-url]]
   [app.contribute-events :refer
    [submit-form
     add-snippet
     on-snippet-textarea-change
     on-how-to-fix-textarea-change
     on-accordion-item-show
     on-click-delete-snippet]]))


(defn fetch-logs []
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
                     (reset! backend-data data)
                     (reset! log (:content (:log data)))
                     (reset! build-id (:build_id data))
                     (reset! build-id-title (:build_id_title data))
                     (reset! build-url (:build_url data))

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

(defn render-snippet [i snippet show?]
  [:div {:class "accordion-item" :key i}
   [:h2 {:class "accordion-header"}
    [:button
     {:class "accordion-button"
      :type "button"
      :data-bs-toggle "collapse"
      :data-bs-target (str "#snippetCollapse" i)
      :aria-controls (str "snippetCollapse" i)}
     (str "Snippet " (+ i 1))]]

   [:div {:id (str "snippetCollapse" i)
          :class ["accordion-collapse collapse" (if show? "show" nil)]
          :data-bs-parent "#accordionSnippets"
          :data-index-number i}

    [:div {:class "accordion-body" :data-index-number i}
     [:textarea
      {:class "form-control"
       :rows "3"
       :placeholder "What makes this snippet relevant?"
       :on-change #(on-snippet-textarea-change %)}]
     [:div {}
      [:button {:type "button"
                :class "btn btn-outline-danger"
                :data-index-number i
                :on-click #(on-click-delete-snippet %)}
       "Delete"]]]]])

(defn render-snippets []
  (doall (for [enumerated-snippet (map-indexed list @snippets)
               :let [i (first enumerated-snippet)
                     snippet (second enumerated-snippet)
                     show? (= (first enumerated-snippet)
                              (- (count @snippets) 1))]
               :when snippet]
           (render-snippet i snippet show?))))

(defn right-column []
  [:<>
   [:div {:class "mb-3"}
    [:label {:class "form-label"} (str @build-id-title ":")]
    [:input {:type "text"
             :class "form-control"
             :value (or @build-id @build-url "")
             :disabled true
             :readOnly true}]]

   [:label {:class "form-label"} "Interesting snippets:"]
   [:br]
   (when @snippets
     [:div {}
      [:button {:class "btn btn-secondary btn-lg" :on-click #(add-snippet)} "Add"]
      [:br]
      [:br]])

   (if @snippets
     [:div {:class "accordion" :id "accordionSnippets"}
      (render-snippets)]

     [:div {:class "card"}
      [:div {:class "card-body"}
       [:h5 {:class "card-title"} "No snippets yet"]
       [:p {:class "card-text"}
        (str "Please select interesting parts of the log files and press the "
             "'Add' button to annotate them")]
       [:button {:class "btn btn-secondary btn-lg"
                 :on-click #(add-snippet)}
        "Add"]]])

   [:div {:class "mb-3"}
    [:label {:class "form-label"} "How to fix the issue?"]
    [:textarea {:class "form-control" :rows 3
                :placeholder (str "Please describe how to fix the issue in "
                                  "order for the build to succeed.")
                :on-change #(on-how-to-fix-textarea-change (.-target %))}]]

   [:div {:class "col-auto row-gap-3" :id "submit"}
    [:label {:class "form-label"} "Ready to submit the results?"]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click #(submit-form)}
     "Submit"]]])

(defn render-jumbotron [id h1 title description icon]
  [:div {:id id :class "py-5 text-center container rounded"}
   [:h1 h1]
   [:p {:class "lead text-body-secondary"} title]
   [:p {:class "text-body-secondary"} description]
   icon])

(defn render-error [title description]
  (render-jumbotron
   "error"
   "Oops!"
   title
   description
   [:i {:class "fa-solid fa-bug"}]))

(defn loading-screen []
  (render-jumbotron
   "loading"
   "Loading"
   "Please wait, fetching logs from the outside world."
   "..."
   [:div {:class "spinner-border", :role "status"}
    [:span {:class "sr-only"} "Loading..."]]))

(defn contribute []
  ;; I don't know why we need to do it this way,
  ;; instead of like :on-click is done
  ;; (js/document.addEventListener "selectionchange" on-selection-change)

  (when (not-empty @snippets)
    (let [accordion (.getElementById js/document "accordionSnippets")]
      (.addEventListener accordion "show.bs.collapse" on-accordion-item-show)))

  (cond
    @error-description
    (render-error @error-title @error-description)

    @files
    (three-column-layout
     (left-column)
     (middle-column)
     (right-column))

    :else
    (loading-screen)))
