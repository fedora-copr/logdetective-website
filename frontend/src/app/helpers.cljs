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

(defn local-storage-enabled []
  (try
    (.getItem js/localStorage "isenabled") true
    (catch js/DOMException _ false)))

(defn local-storage-get [name]
  (when (local-storage-enabled)
    (.getItem js/localStorage name)))

(defn query-params-get [name]
  (-> js/window
      .-location
      .-search
      js/URLSearchParams.
      (.get name)))

(defn local-storage-error []
  {:title "Local storage is blocked by the browser"
   :description
   (str "Log Detective needs to upload the file to a localStorage in order "
        "to work properly. Please check your browser privacy settings.")})

(defn safe [text]
  (.encode html-entities text))

(defn redirect [url]
  (set! (.-href (.-location js/window)) url))

(defn change-url
  "Change URL without a full page reload or redirect"
  [url]
  (.pushState (.-history js/window) nil nil url))

(defn upload-error [error-msg]
  {:title "Upload error"
   :description
   (str "Your browser has encountered and error while attempting an upload."
        error-msg)})
