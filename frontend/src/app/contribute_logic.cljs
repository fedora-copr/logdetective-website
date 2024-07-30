(ns app.contribute-logic
  (:require
   [app.contribute-atoms :refer [files]]))

(defn file-id [name]
  ;; TODO Replace implementation with index-of-file and move to editor
  (loop [i 0 files @files]
    (cond
      (empty? files) nil
      (= name (:name (first files))) i
      :else (recur (inc i) (rest files)))))
