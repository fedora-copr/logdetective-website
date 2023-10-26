(ns app.helpers)

(defn current-path []
  (.-pathname (.-location js/window)))

(defn fontawesome-icon [name]
  [:i {:class ["fa-regular" name]}])

(defn remove-trailing-slash [text]
  (clojure.string/replace text #"/$" ""))
