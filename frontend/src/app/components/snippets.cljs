(ns app.components.snippets
  (:require
   [reagent.core :as r]
   [clojure.string :as str]
   [reagent.dom.server :refer [render-to-string]]))

(def snippets (r/atom []))

(defn snippet-color [id]
  (let [colors ["#D4C5F9"
                "#C2E0C6"
                "#C5DEF5"
                "#FEF2C0"
                "#BFD4F2"
                "#BFDADC"
                "#E99695"]]
    (nth colors (mod id (count colors)))))

(defn snippet-color-square [color]
  [:span {:style {:width 15
                  :height 15
                  :margin-right 10
                  :background-color color}}])

(defn clear-selection []
  ;; Generated from
  ;; https://stackoverflow.com/a/13415236/3285282
  (cond
    (.-getSelection js/window) (.removeAllRanges (.getSelection js/window))
    (.-selection js/document) (.empty (.-selection js/document))
    :else nil))

(defn selection-contains-snippets? []
  (let [selection (.getSelection js/window)
        spans (.getElementsByClassName js/document "snippet")]
    (when (not-empty spans)
      (some (fn [span] (.containsNode selection span true))
            spans))))

(defn highlight-current-snippet [color]
  ;; The implementation heavily relies on JavaScript interop. I took the
  ;; "Best Solution" code from:
  ;; https://itecnote.com/tecnote/javascript-selected-text-highlighting-prob/
  ;; and translated it from Javascript to ClojureScript using:
  ;; https://roman01la.github.io/javascript-to-clojurescript/
  ;; TODO This can be easily refactored to use `highlight-text'
  (let [rangee (.getRangeAt (.getSelection js/window) 0)
        span (.createElement js/document "span")]
    (set! (.-className span) "snippet")
    (set! (.-style span) (str "background-color: " color))
    (set! (.-id span) (str "snippet-" (count @snippets)))
    (set! (.-index-number (.-dataset span)) (count @snippets))
    (.appendChild span (.extractContents rangee))
    (.insertNode rangee span)))

(defn highlight-text [id text comment color]
  (render-to-string
   [:span {:class "snippet"
           :id id
           :title comment
           :style {:background-color color}
           :dangerouslySetInnerHTML
           {:__html text}}]))

(defn selection-node-id []
  (let [base (.-anchorNode (.getSelection js/window))]
    (if base (.-id (.-parentNode base)) nil)))

(defn add-snippet [files active-file]
  ;; The `files` and `active-file` parameters needs to be passed as atom
  ;; references, not their dereferenced value
  (when (and (= (.-type (js/window.getSelection)) "Range")
             (= (selection-node-id) "log")
             (not (selection-contains-snippets?)))

    (let [color (snippet-color (count @snippets))]
      (highlight-current-snippet color)

      ;; Save the log with highlights, so they are remembered when switching
      ;; between file tabs
      (let [log (.-innerHTML (.getElementById js/document "log"))]
        (reset! files (assoc-in @files [@active-file :content] log)))

      (let [selection (.getSelection js/window)
            content (.toString selection)

            ;; Index of the first snippet character. It is much harder to get
            ;; the correct value than expected because of number of browser
            ;; inconsistencies. See `offset.js` for more information.
            start (js/getAbsoluteOffsetInContainer "log")

            ;; Index of the last snippet character. When parsing in python,
            ;; you can check that text == content[start:end]
            end (+ start (count content))

            snippet
            {:text content
             :start-index start
             :end-index end
             :comment nil
             :color color
             :file (:name (get @files @active-file))}]
        (swap! snippets conj snippet)))
    (clear-selection)))

(defn add-snippet-from-backend-map [files file-index map]
  (let [snippet
        {:text (:text map)
         :start-index (:start_index map)
         :end-index (:end_index map)
         :comment (:user_comment map)
         :file (:name (get files file-index))
         :color (snippet-color (count @snippets))}]
    (swap! snippets conj snippet)))

;; For some reason, compiler complains it cannot infer type of the `target`
;; variable, so I am specifying it as a workaround
(defn on-snippet-textarea-change [^js/Event event]
  (let [target (.-target event)
        index (int (.-indexNumber (.-dataset (.-parentElement target))))
        value (.-value target)]
    (reset! snippets (assoc-in @snippets [index :comment] value))))

(defn on-click-delete-snippet [^js/Event event]
  (let [target (.-target event)
        snippet-id (-> target
                       .-parentElement
                       .-parentElement
                       .-dataset
                       .-indexNumber
                       int)]

    ;; We don't want to remove the element entirely because we want to preserve
    ;; snippet numbers that follows
    (swap! snippets assoc snippet-id nil)

    ;; Remove the highlight
    (let [span (.getElementById js/document (str "snippet-" snippet-id))
          text (.-innerHTML span)]
      (.replaceWith span text))))

(defn scroll-to-snippet [file snippet]
  (let [log (.getElementById js/document "log")
        lines (-> file
                  (:content)
                  (subs 0 (:start-index snippet))
                  (str/split #"\n")
                  (count)
                  (- 1))

        ;; This is the line height in pixels. The applicable CSS line-height
        ;; is `--bs-body-line-height' which is 1.5 and the font-size is
        ;; 0.875em which equals to 14px.
        lineheight (* 1.5 14)

        ;; We want to scroll few more lines so that the snippet isn't at the
        ;; exact top of the editor and it is more close to the center
        offset (* 5 lineheight)
        pixels (- (* lines lineheight) offset)]
    (set! (.-scrollTop log) pixels)))
