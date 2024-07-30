(ns app.helpers
  (:require
   [clojure.string :as str]
   ["html-entities" :as html-entities]))

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

(defn local-storage-enabled []
  (try
    (.getItem js/localStorage "isenabled") true
    (catch js/DOMException _ false)))

(defn local-storage-get [name]
  (when (local-storage-enabled)
    (.getItem js/localStorage name)))

(defn local-storage-error []
  {:title "Local storage is blocked by the browser"
   :description
   (str "Log Detective needs to upload the file to a localStorage in order "
        "to work properly. Please check your browser privacy settings.")})

(defn safe [text]
  (.encode html-entities text))
