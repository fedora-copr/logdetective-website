(ns app.review.logic
  (:require
   [app.common.state :refer [files]]))

(defn index-of-file [name]
  (.indexOf (map (fn [x] (:name x)) @files) name))
