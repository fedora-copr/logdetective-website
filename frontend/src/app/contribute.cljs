(ns app.contribute
  (:require [reagent.core :as r]
            [clojure.string :as str]
            [cljs.core.match :refer-macros [match]]
            [lambdaisland.fetch :as fetch]
            [web.Range :refer [surround-contents]]))


(def how-to-fix (r/atom nil))
(def snippets (r/atom []))
(def files (r/atom nil))
(def active-file (r/atom 0))

(def backend-data (r/atom nil))
(def log (r/atom nil))
(def build-id (r/atom nil))
(def build-id-title (r/atom nil))


(defn current-path []
  (.-pathname (.-location js/window)))

(defn fetch-logs []
  (let [url (str "/frontend" (current-path))]
    (-> (fetch/get url {:accept :json :content-type :json})
        (.then (fn [resp] (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data]
                 (reset! backend-data data)
                 (reset! log (:content (:log data)))
                 (reset! build-id (:build_id data))
                 (reset! build-id-title (:build_id_title data))
                 (reset! files (:logs data)))))))

(defn submit-form []
  (let [url (str "/frontend" (current-path))
        body {:how-to-fix @how-to-fix
              :snippets @snippets}]
    (-> (fetch/post url {:accept :json :content-type :json :body body})
        (.then (fn [resp] (-> resp :body (js->clj :keywordize-keys true))))
        (.then (fn [data] data)))))

(defn init-data []
  (fetch-logs)
  ;; (reset!
  ;;  files
  ;;  [{:name "builder-live.log"
  ;;    :content nil}

  ;;   {:name "import.log"
  ;;    :content nil}

  ;;   {:name "backend.log"
  ;;    :content nil}

  ;;   {:name "root.log"
  ;;    :content nil}])

  ;; (reset!
  ;;  snippets
  ;;  ["There is an exception, so that's the error, right?"
  ;;   "The python3-specfile package was not available in 0.21.0 version or higher."
  ;;   "Third snippet"])

  )


(defn on-how-to-fix-textarea-change [target]
  (reset! how-to-fix (.-value target)))

;; For some reason, compiler complains it cannot infer type of the `target`
;; variable, so I am specifying it as a workaround
(defn on-snippet-textarea-change [^js/HTMLTextAreaElement target]
  (let [index (int (.-indexNumber (.-dataset target)))
        value (.-value target)]
    (reset! snippets (assoc-in @snippets [index :comment] value))))

(defn render-tab [name, key]
  (let [active? (= name (:name (get @files @active-file)))]
    [:li {:class "nav-item" :key key}
     [:a {:class ["nav-link" (if active? "active" nil)]
          :on-click #(reset! active-file key)
          :href "#"}
      name]]))

(defn render-tabs []
  [:ul {:class "nav nav-tabs"}
   (doall (for [[i file] (map-indexed list @files)]
            (render-tab (:name file) i)))])

(defn fontawesome-icon [name]
  [:i {:class ["fa-regular" name]}])

(defn instructions-item [done? text]
  (let [class (if done? "done" "todo")
        icon-name (if done? "fa-square-check" "fa-square")]
    [:li {:class class}
     [:span {:class "fa-li"}
      (fontawesome-icon icon-name)]
     text]))

(defn render-left-column []
  [:div {:class "col-3" :id "left-column"}
   [:h4 {} "Instructions"]
   [:ul {:class "fa-ul"}
    (instructions-item
     (not-empty @files)
     [:<>
      (str "We fetched logs for " @build-id-title " ")
      [:a {:href "#"} (str "#" @build-id)]])

    ;; Maybe "Write why do you think the build failed"

    (instructions-item
     (not-empty @how-to-fix)
     "Describe how to fix the issue")

    (instructions-item
     (not-empty @snippets)
     "Find log snippets relevant to the failure")

    (instructions-item
     (not-empty @snippets)
     "Anotate snippets by selecting them, and clicking 'Anotate selection'")

    (instructions-item
     (not-empty (:comment (first @snippets)))
     "Describe what makes the snippets interesting")

    (instructions-item nil "Submit")]])

(defn render-middle-column []
  [:div {:class "col-6"}
   (render-tabs)
   (let [log (:content (get @files @active-file))]
     [:pre {:id "log" :dangerouslySetInnerHTML {:__html log}}])])

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

    [:div {:class "accordion-body"}
     [:textarea
      {:class "form-control"
       :rows "3"
       :placeholder "What makes this snippet relevant?"
       :data-index-number i
       :on-change #(on-snippet-textarea-change (.-target %))}]
     [:div {}
      [:button {:type "button" :class "btn btn-outline-danger"} "Delete"]]]]])

(defn render-snippets []
   (doall (for [enumerated-snippet (map-indexed list @snippets)]
            (render-snippet (first enumerated-snippet)
                            (second enumerated-snippet)
                            (= (first enumerated-snippet)
                               (- (count @snippets) 1))))))

(defn highlight-current-snippet []
  ;; The implementation heavily relies on JavaScript interop. I took the
  ;; "Best Solution" code from:
  ;; https://itecnote.com/tecnote/javascript-selected-text-highlighting-prob/
  ;; and translated it from Javascript to ClojureScript using:
  ;; https://roman01la.github.io/javascript-to-clojurescript/
  (def rangee (.getRangeAt (.getSelection js/window) 0))
  (def span (.createElement js/document "span"))
  (set! (.-className span) "snippet")
  (.appendChild span (.extractContents rangee))
  (.insertNode rangee span))

(defn clear-selection []
  ;; Generated from
  ;; https://stackoverflow.com/a/13415236/3285282
  (cond
    (.-getSelection js/window) (.removeAllRanges (.getSelection js/window))
    (.-selection js/document) (.empty (.-selection js/document))
    :else nil))

(defn selection-node-id []
  (.-id (.-parentNode (.-baseNode (.getSelection js/window)))))

(defn add-snippet []
  (when (= (selection-node-id) "log")
    (highlight-current-snippet)

    ;; Save the log with highlights, so they are remembered when switching
    ;; between file tabs
    (let [log (.-innerHTML (.getElementById js/document "log"))]
      (reset! files (assoc-in @files [@active-file :content] log)))

    (let [snippet
          {:text (.toString (.getSelection js/window))
           :comment nil
           :file (:name (get @files @active-file))}]
      (swap! snippets conj snippet))

    (clear-selection)))

(defn render-right-column []
  [:div {:class "col-3" :id "right-column"}
   [:div {:class "mb-3"}
    [:label {:class "form-label"} (str @build-id-title " ID")]
    [:input {:type "text" :class "form-control" :value (or @build-id "")
             :disabled true :readOnly true}]]

   [:div {:class "mb-3"}
    [:label {:class "form-label"} "How to fix the issue?"]
    [:textarea {:class "form-control" :rows 3
                :placeholder (str "Please describe how to fix the issue in "
                                  "order for the build to succeed.")
                :on-change #(on-how-to-fix-textarea-change (.-target %))}]]

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

   [:div {:class "col-auto row-gap-3" :id "submit"}
    [:label {:class "form-label"} "Ready to submit the results?"]
    [:br]
    [:button {:type "submit"
              :class "btn btn-primary btn-lg"
              :on-click #(submit-form)}
     "Submit"]]])

;; We might need this function for enabling/disabling the "new snippet" button
;; based on whether user selected something (within the <pre>log</pre> area)
;; (defn on-selection-change [event]
;;   (let [selection (js/window.getSelection)]
;;     (js/console.log selection)
;;     (js/console.log selection.anchorOffset)
;;     (js/console.log selection.focusOffset)))

(defn file-id [name]
  (loop [i 0 files @files]
    (cond
      (empty? files) nil
      (= name (:name (first files))) i
      :else (recur (inc i) (rest files)))))

;; For some reason, compiler complains it cannot infer type of the `event`
;; variable, so I am specifying it as a workaround
(defn on-accordion-item-show [^js/Event event]
  (let [snippet-id (int (.-indexNumber (.-dataset (.-target event))))
        snippet (nth @snippets snippet-id)
        file-name (:file snippet)]
  (reset! active-file (file-id file-name))))

(defn contribute []
  ;; I don't know why we need to do it this way,
  ;; instead of like :on-click is done
  ;; (js/document.addEventListener "selectionchange" on-selection-change)

  (when (not-empty @snippets)
    (let [accordion (.getElementById js/document "accordionSnippets")]
      (.addEventListener accordion "show.bs.collapse" on-accordion-item-show)))

  ;; TODO Else fancy loading screen
  (if @files
    [:div {:class "row"}
     (render-left-column)
     (render-middle-column)
     (render-right-column)]))
