(ns app.review.core
  (:require
   [clojure.set :refer [rename-keys]]
   [ajax.core :refer [GET POST]]
   [clojure.string :as str]
   [malli.core :as m]
   [app.helpers :refer
    [safe
     fontawesome-icon]]
   [app.editor.core :refer [editor active-file]]
   [app.components.accordion :refer [accordion]]
   [app.components.jumbotron :refer
    [render-error
     loading-screen
     render-jumbotron]]
   [app.three-column-layout.core :refer
    [three-column-layout
     instructions-item
     instructions
     status-panel]]
   [app.components.snippets :refer
    [snippets
     add-snippet
     add-snippet-from-backend-map
     on-snippet-textarea-change
     on-click-delete-snippet
     snippet-color
     snippet-color-square
     highlight-text
     scroll-to-snippet]]
   [app.review.logic :refer [index-of-file]]
   [app.review.events :refer
    [on-accordion-item-show
     vote on-vote-button-click
     on-change-form-input]]
   [app.review.atoms :refer
    [files
     raw-files
     error-description
     error-title
     status
     form
     votes]]))

(def InputSchema
  (let [File [:map [:name :string] [:content :string]]]
    [:map {:closed true}
     [:username [:maybe :string]] ;; TODO We don't want username from backend
     [:id :string]
     [:fail_reason :string]
     [:how_to_fix :string]
     [:container_file [:maybe File]]
     [:spec_file [:maybe File]]
     [:logs [:map-of :any File]]]))

(defn highlight-snippets-withing-log [log]
  (let [original-order (:snippets log)
        snippets
        (->> (:snippets log)
             (sort-by :start_index)
             (map
              (fn [itm]
                (let [idx (.indexOf original-order itm)
                      text (subs (:content log)
                                 (:start_index itm)
                                 (:end_index itm))
                      text (highlight-text (str "snippet-" idx)
                                           (safe text)
                                           (:user_comment itm)
                                           (:color (nth @snippets idx)))]
                  (assoc itm :text text)))))

        content
        (->>
         [(safe (subs (:content log) 0 (:start_index (first snippets))))
          (for [[a b] (partition-all 2 snippets)]
            [(:text a)
             (when b
               (safe (subs (:content log) (:end_index a) (:start_index b)))
               (:text b))])
          (safe (subs (:content log) (:end_index (last snippets))))]
         (flatten)
         (apply str))]

    (assoc log :content content)))

(defn handle-validated-backend-data [data]
  (reset! form (assoc @form :id (:id data)))
  (reset! form (assoc @form :how-to-fix (:how_to_fix data)))
  (reset! form (assoc @form :fail-reason (:fail_reason data)))

  ;; First we need to set the files, so that snippets can point to them. We
  ;; will highlight them later
  (reset! files (vec (vals (:logs data))))
  (reset! raw-files (vec (vals (:logs data))))

  ;; Parse snippets from backend and store them to @snippets
  (doall (for [file (vals (:logs data))
               :let [file-index (index-of-file (:name file))]]
           (doall (for [snippet (:snippets file)]
                    (add-snippet-from-backend-map
                     @files
                     file-index
                     snippet)))))

  (reset! snippets
          (vec (map-indexed
                (fn [i x] (assoc x :color (snippet-color i)))
                @snippets)))

  (reset! files (vec (map highlight-snippets-withing-log (vals (:logs data)))))

  (when @snippets
    (reset! active-file (index-of-file (:file (last @snippets))))))

(defn handle-backend-error [title description]
  (reset! status "error")
  (reset! error-title title)
  (reset! error-description description))

(defn handle-validation-error [title description]
  ;; Go back to "has files" state, let users fix
  ;; validation errors
  (reset! status nil)
  (reset! error-title title)
  (reset! error-description description))

(defn result-id-from-url []
  (let [split (-> js/window .-location .-href (str/split "/review/"))]
    (when (> (count split) 1)
      (last split))))

(defn init-data-review []
  (GET (str "/frontend/review/" (or (result-id-from-url)  "random"))
    :response-format :json
    :keywords? true

    :error-handler
    (fn [error]
      (handle-backend-error
       (:error (:response error))
       (:description (:response error))))

    :handler
    (fn [data]
      (if (m/validate InputSchema data)
        (handle-validated-backend-data data)
        (handle-backend-error
         "Invalid data"
         "Got invalid data from the backend. This is likely a bug.")))))

(defn submit-form []
  (let [body {:id (:id @form)
              :username (if (:fas @form) (str "FAS:" (:fas @form)) nil)
              :fail_reason {:text (:fail-reason @form)
                            :vote (:fail-reason @votes)}
              :how_to_fix  {:text (:how-to-fix @form)
                            :vote (:how-to-fix @votes)}
              :snippets
              (vec (map-indexed
                    (fn [i x]
                      (let [k (keyword (str "snippet-" i))
                            vote (k @votes 0)]
                        (rename-keys
                         (assoc x :vote vote)
                         {:start-index :start_index
                          :end-index :end_index
                          :user-comment :comment})))
                    (remove nil? @snippets)))}]

    ;; Remember the username, so we can prefill it the next time
    ;; TODO See PR #130
    (when (:fas @form)
      (.setItem js/localStorage "fas" (:fas @form)))

    (reset! status "submitting")

    (POST "/frontend/review"
      {:params body
       :response-format :json
       :format :json
       :keywords? true

       :error-handler
       (fn [error]
         (handle-validation-error
          (:error (:response error))
          (:description (:response error))))

       :handler
       (fn [_]
         (reset! status "submitted"))})))

(defn left-column []
  (instructions
   [(instructions-item
     true
     "We fetched a random sample from our collected data set")

    (instructions-item
     (>= (count (dissoc @votes :how-to-fix :fail-reason)) (count @snippets))
     "Go through all snippets and either upvote or downvote them")

    (instructions-item
     (not= (:fail-reason @votes) 0)
     "Is the explanation why did the build fail correct?")

    (instructions-item
     (not= (:how-to-fix @votes) 0)
     "Is the explanation how to fix the issue correct?")

    (instructions-item nil "Submit")]))

(defn on-editor-rendered [element]
  (when element
    (scroll-to-snippet
     (get @raw-files @active-file)
     (last @snippets))))

(defn middle-column []
  [:div {:ref on-editor-rendered}
   (editor @files)])

(defn buttons [name]
  (let [key (keyword name)]
    [[:button {:type "button"
               :class ["btn btn-vote" (if (> (key @votes) 0)
                                        "btn-primary"
                                        "btn-outline-primary")]
               :on-click #(on-vote-button-click key 1)}
      (fontawesome-icon "fa-thumbs-up")]
     [:button {:type "button"
               :class ["btn btn-vote" (if (< (key @votes) 0)
                                        "btn-danger"
                                        "btn-outline-danger")]
               :on-click #(on-vote-button-click key -1)}
      (fontawesome-icon "fa-thumbs-down")]]))

(defn snippet [text index color]
  (when color
    (let [name (str "snippet-" index)]
      {:title [:<> (snippet-color-square color) "Snippet"]
       :body
       [:textarea
        {:class "form-control"
         :rows "3"
         :placeholder "What makes this snippet relevant?"
         :value text
         :on-change #(do (on-snippet-textarea-change %)
                         (vote (keyword name) 1))}]
       :buttons
       (conj (buttons name)
             [:button {:type "button"
                       :class ["btn btn-vote btn-outline-danger"]
                       :on-click #(on-click-delete-snippet %)}
              (fontawesome-icon "fa-trash-can")])})))

(defn card [title text name placeholder]
  [:div {:class "card review-card"}
   [:div {:class "card-body"}
    [:h6 {:class "card-title"} title]
    [:textarea {:class "form-control" :rows 3
                :value text
                :placeholder placeholder
                :name name
                :on-change #(do (on-change-form-input %)
                                (vote (keyword name) 1))}]
    [:div {:class "btn-group"}
     (into [:<>] (buttons name))]]])

(defn right-column []
  [:<>
   [:label {:class "form-label"} "Your FAS username:"]
   [:input {:type "text"
            :class "form-control"
            :placeholder "Optional - Your FAS username"
            ;; TODO See PR #130
            :value (or (:fas @form) (.getItem js/localStorage "fas"))
            :name "fas"
            :on-change #(on-change-form-input %)}]

   [:label {:class "form-label"} "Interesting snippets:"]
   (when (not-empty @snippets)
     [:div {}
      [:button {:class "btn btn-secondary btn-lg"
                :on-click #(add-snippet files active-file)} "Add"]
      [:br]])

   [:label {:class "form-label"}
    "You can edit existing snippets. This will automatically upvote them."]
   (accordion
    "accordionItems"
    (vec (map-indexed (fn [i x] (snippet (:comment x) i (:color x))) @snippets)))

   (when (empty? @snippets)
     [:div {:class "card" :id "no-snippets"}
      [:div {:class "card-body"}
       [:h5 {:class "card-title"} "No snippets yet"]
       [:p {:class "card-text"}
        (str "Please select interesting parts of the log files and press the "
             "'Add' button to annotate them")]
       [:button {:class "btn btn-secondary btn-lg"
                 :on-click #(add-snippet files active-file)}
        "Add"]]])

   [:br]
   (card
    "Why did the build fail?"
    (:fail-reason @form)
    "fail-reason"
    "Please describe what caused the build to fail.")

   [:br]
   (card
    "How to fix the issue?"
    (:how-to-fix @form)
    "how-to-fix"
    (str "Please describe how to fix the issue in "
         "order for the build to succeed."))

   [:div {}
    [:label {:class "form-label"} "Ready to submit the results?"]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click #(submit-form)}
     "Submit"]]])

(defn render-succeeded []
  (render-jumbotron
   "succeeded"
   "Thank you!"
   "Successfully submitted, thank you for your review."
   "..."
   [:a {:type "submit"
        :class "btn btn-primary btn-lg"
        :href "/review"}
    [:<> [:i {:class "fa-solid fa-magnifying-glass"}] " Review another report"]]))

(defn review []
  ;; The js/document is too general, ideally we would like to limit this
  ;; only to #accordionItems but it doesn't exist soon enough
  (.addEventListener js/document "show.bs.collapse" on-accordion-item-show)

  (cond
    (= @status "error")
    (render-error @error-title @error-description)

    (= @status "submitted")
    (render-succeeded)

    @files
    (three-column-layout
     (left-column)
     (middle-column)
     (right-column)
     (status-panel @status @error-title @error-description))

    :else
    (loading-screen "Please wait, fetching logs from our dataset.")))
