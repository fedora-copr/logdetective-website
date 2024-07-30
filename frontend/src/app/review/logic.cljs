(ns app.review.logic
  (:require
   [app.review.atoms :refer [files]]))

(defn index-of-file [name]
  (.indexOf (map (fn [x] (:name x)) @files) name))
