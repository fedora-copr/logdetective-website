(ns app.contribute
  (:require
   [lambdaisland.fetch :as fetch]
   ["html-entities" :as html-entities]
   [app.helpers :refer
    [current-path
     remove-trailing-slash
     local-storage-enabled
     local-storage-error
     fontawesome-icon]]
   [app.three-column-layout.core :refer
    [three-column-layout
     instructions-item
     instructions
     status-panel]]
   [app.editor.core :refer [editor active-file]]
   [app.components.jumbotron :refer
    [render-error
     loading-screen
     render-jumbotron]]
   [app.components.accordion :refer [accordion]]
   [app.components.snippets :refer
    [snippets
     add-snippet
     snippet-color-square
     selection-node-id
     on-click-delete-snippet
     on-snippet-textarea-change]]
   [app.contribute-atoms :refer
    [how-to-fix
     status
     files
     spec
     container
     error-description
     error-title
     backend-data
     log
     build-id
     build-id-title
     build-url
     text-in-log-selected?
     ok-status]]
   [app.contribute-events :refer
    [submit-form
     on-how-to-fix-textarea-change
     on-change-fail-reason
     on-accordion-item-show]]))

(defn set-atoms
  "Set atoms to contain fields from `data` map.
  This map is either constructed from direct file upload or from the backend.
  Backend provides `ContributeResponseSchema` structure."
  [data]

  (reset! backend-data data)
  (reset! log (:content (:log data)))
  (reset! build-id (:build_id data))
  (reset! build-id-title (:build_id_title data))
  (reset! build-url (:build_url data))
  (reset! spec (:spec_file data))
  (reset! container (:container_file data))
  (reset!
   files
   (vec (map (fn [log]
               ;; We must html encode all HTML characters
               ;; because we are going to render the log
               ;; files dangerously
               (update log :content #(.encode html-entities %)))
             (:logs data))))

  (reset! error-title nil)
  (reset! error-description nil)
  (reset! ok-status nil))

(defn fetch-logs-backend
  "Fetch logs and other associated data from from backend.
  Received map is defined in backend as `ContributeResponseSchema` object."
  []

  (let [url (remove-trailing-slash (str "/frontend" (current-path)))]
    (-> (fetch/get url {:accept :json :content-type :json})
        (.then (fn [resp]
                 (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data]
                 (if (:error data)
                   (do
                     (reset! status "error")
                     (reset! error-title (:error data))
                     (reset! error-description (:description data)))
                   (set-atoms data)))))))

(defn fetch-logs-upload
  "Fetch logs and other associated data from direct upload to the website."
  []

  (if (local-storage-enabled)
    (let [data {:build_id_title "Upload"
                :logs [{:name (.getItem js/localStorage "name")
                        :content (.getItem js/localStorage "content")}]}]
      (set-atoms data))
    (do
      (reset! status "error")
      (reset! error-title (:title (local-storage-error)))
      (reset! error-description (:description (local-storage-error))))))

(defn init-data []
  (if (= (remove-trailing-slash (current-path))  "/contribute/upload")
    (fetch-logs-upload)
    (fetch-logs-backend)))

(defn left-column []
  (instructions
   [(instructions-item
     (not-empty @files)

     (cond
       (contains? #{"URL" "Container log"} @build-id-title)
       [:<>
        (str "We fetched logs from ")
        [:a {:href @build-url} "this URL"]]

       (= @build-id-title "Upload")
       [:<>
        (str "Upload a log file from your computer")]

       :else
       [:<>
        (str "We fetched logs for " @build-id-title " ")
        [:a {:href @build-url} (str "#" @build-id)]]))

    ;; Maybe "Write why do you think the build failed"

    (instructions-item
     (not-empty @snippets)
     "Find log snippets relevant to the failure")

    (instructions-item
     (not-empty @snippets)
     "Create snippets by selecting them and clicking 'Add', then writing annotations")

    (instructions-item
     (some not-empty (map :comment @snippets))
     "Describe what makes the snippets interesting")

    (instructions-item
     (not-empty @how-to-fix)
     "Describe how to fix the issue")

    (instructions-item nil "Submit")]))

(defn middle-column []
  (editor @files))

(defn accordion-snippet [snippet]
  (when snippet
    {:title [:<> (snippet-color-square (:color snippet)) "Snippet"]
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

(defn add-button []
  (let [title (if @text-in-log-selected?
                "Add the selected snippet"
                "Select a relevant text in the log file first")
        color (if @text-in-log-selected? "btn-primary" "btn-secondary")]
    [:button
     {:class ["btn" "btn-lg" color]
      :on-click #(add-snippet files active-file)
      :title title}
     "Add"]))

(defn right-column
  "Render right column."
  []
  [:<>

   [:label {:class "form-label"} "Interesting snippets:"]
   (when (not-empty @snippets)
     [:div {}
      (add-button)
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
       (add-button)]])

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
    [:label {:class "form-label"} "Ready to submit the results? "
     "By submitting this form, you agree that your input "
     "will be covered by " [:a {:href "http://creativecommons.org/"} "CC0"] " and used to create dataset "
     "released under " [:a {:href "https://cdla.dev/permissive-2-0/"} "CDLA-Permissive-2.0"] " license."]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click #(submit-form)
              :disabled (or (empty? @how-to-fix) (some empty (map :comment @snippets)))}
     "Submit"]]])

(defn render-succeeded [ok-response]
  (render-jumbotron
   "succeeded"
   "Thank you!"
   "Successfully submitted, thank you for your contribution."
   [:p
    "You can review it here: "
    [:a
     {:href
      (:review_url_website ok-response)}
     (:review_url_website ok-response)]]
   [:a {:type "submit"
        :class "btn btn-primary btn-lg"
        :href "/"}
    [:<> (fontawesome-icon "fa-plus") " Add another log"]]))

(defn on-text-selected []
  (reset!
   text-in-log-selected?
   (and
    (= (.-type (js/window.getSelection)) "Range")
    (= (selection-node-id) "log"))))

(defn contribute []
  ;; I don't know why we need to do it this way,
  ;; instead of like :on-click is done
  ;; (js/document.addEventListener "selectionchange" on-selection-change)

  ;; The existing states
  ;; -------------------
  ;; "loading" (status=nil, the default)
  ;;    A separate page. The logs are being downloaded from backend (backend
  ;;    downloads the data external services)
  ;; "has files" (status=nil, @files loaded, opt-in @error-{title,description})
  ;;    Successfully loaded files.  Contributions are being added.  If @error-*
  ;;    atoms are set, they are rendered at the top of the page.
  ;; "submitting" (ditto ^^^, but status="submitting")
  ;;    The form data is being uploaded, but form stays in an editable state so
  ;;    we can recover (and e.g. fix the server-side validation errors).
  ;; "submitted" (status="submitted")
  ;;    A separate "thank you" page with URL to annotated log in review interface.
  ;; "error page" (status="error")
  ;;    A separate error page, e.g. for failed loading.
  (cond
    (= @status "error")
    (render-error @error-title @error-description)

    (= @status "submitted")
    (render-succeeded @ok-status)

    @files
    (do
      (.addEventListener js/document "selectionchange" on-text-selected)
      (when (not-empty @snippets)
        (let [accordion (.getElementById js/document "accordionItems")]
          (.addEventListener accordion "show.bs.collapse" on-accordion-item-show)))

      (three-column-layout
       (left-column)
       (middle-column)
       (right-column)
       (status-panel @status @error-title @error-description)))

    :else
    (loading-screen "Please wait, fetching logs from the outside world.")))
