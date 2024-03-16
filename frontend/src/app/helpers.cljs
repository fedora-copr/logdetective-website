(ns app.helpers
  (:require
   [clojure.string :as str]))

(defn current-path []
  (.-pathname (.-location js/window)))

(defn fontawesome-icon [name]
  [:i {:class ["fa-regular" name]}])

(defn remove-trailing-slash [text]
  (clojure.string/replace text #"/$" ""))

(defn previous-siblings [node]
  (let [sibling (.-previousSibling node)]
    (if-not sibling
      []
      (conj (previous-siblings sibling) sibling))))
