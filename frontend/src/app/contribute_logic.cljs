(ns app.contribute-logic
  (:require
   [app.contribute-atoms :refer
    [files
     snippets]]))


(defn clear-selection []
  ;; Generated from
  ;; https://stackoverflow.com/a/13415236/3285282
  (cond
    (.-getSelection js/window) (.removeAllRanges (.getSelection js/window))
    (.-selection js/document) (.empty (.-selection js/document))
    :else nil))

(defn highlight-current-snippet []
  ;; The implementation heavily relies on JavaScript interop. I took the
  ;; "Best Solution" code from:
  ;; https://itecnote.com/tecnote/javascript-selected-text-highlighting-prob/
  ;; and translated it from Javascript to ClojureScript using:
  ;; https://roman01la.github.io/javascript-to-clojurescript/
  (def rangee (.getRangeAt (.getSelection js/window) 0))
  (def span (.createElement js/document "span"))
  (set! (.-className span) "snippet")
  (set! (.-id span) (str "snippet-" (count @snippets)))
  (set! (.-index-number (.-dataset span)) (count @snippets))
  (.appendChild span (.extractContents rangee))
  (.insertNode rangee span))

(defn selection-node-id []
  (let [base (.-anchorNode (.getSelection js/window))]
    (if base (.-id (.-parentNode base)) nil)))

(defn file-id [name]
  (loop [i 0 files @files]
    (cond
      (empty? files) nil
      (= name (:name (first files))) i
      :else (recur (inc i) (rest files)))))

(defn selection-contains-snippets? []
  (let [selection (.getSelection js/window)
        spans (.getElementsByClassName js/document "snippet")]
    (when (not-empty spans)
     (some (fn [span] (.containsNode selection span true))
           spans))))
