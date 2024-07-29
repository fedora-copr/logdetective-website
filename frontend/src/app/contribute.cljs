(ns app.contribute
  (:require
   [lambdaisland.fetch :as fetch]
   ["html-entities" :as html-entities]
   [app.helpers :refer
    [current-path
     remove-trailing-slash
     local-storage-enabled
     local-storage-get
     local-storage-error]]
   [app.three-column-layout.core :refer
    [three-column-layout
     instructions-item
     instructions]]
   [app.editor.core :refer [editor]]
   [app.components.jumbotron :refer
    [render-error
     loading-screen
     loading-icon
     render-succeeded]]
   [app.components.accordion :refer [accordion]]
   [app.contribute-atoms :refer
    [how-to-fix
     status
     snippets
     files
     spec
     container
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

(defn set-atoms [data]
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
  (reset! error-description nil))

(defn fetch-logs-backend []
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

(defn fetch-logs-upload []
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
     (not-empty (:comment (first @snippets)))
     "Describe what makes the snippets interesting")

    (instructions-item
     (not-empty @how-to-fix)
     "Describe how to fix the issue")

    (instructions-item nil "Submit")]))

(defn display-error-middle-top []
  (when @error-description
    [:div
     [:div {:class "alert alert-danger alert-dismissible fade show text-center"}
      [:strong @error-title]
      [:p @error-description]
      [:button {:type "button" :class "btn-close" :data-bs-dismiss "alert"}]]]))

(defn notify-being-uploaded []
  (when (= @status "submitting")
    [:h2 {:class "lead text-body-secondary"}
     (loading-icon)
     "  Uploading ..."]))

(defn middle-column []
  [:<>
   (or
    (notify-being-uploaded)
    (display-error-middle-top))
   [editor @files]])

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
             :value (or @fas (local-storage-get "fas"))
             :on-change #(on-change-fas %)}]]

   [:label {:class "form-label"} "Interesting snippets:"]
   (when (not-empty @snippets)
     [:div {}
      [:button {:class "btn btn-secondary btn-lg" :on-click #(add-snippet)} "Annotate selection"]
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
        "Annotate selection"]]])

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
     "can be used for teaching AI and that the data are "
     "available under " [:a {:href "https://cdla.dev/permissive-2-0/"} "CDLA-Permissive-2.0"] " license."]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click #(submit-form)}
     "Submit"]]])

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
  ;;    A separate "thank you" page.
  ;; "error page" (status="error")
  ;;    A separate error page, e.g. for failed loading.
  (cond
    (= @status "error")
    (render-error @error-title @error-description)

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
