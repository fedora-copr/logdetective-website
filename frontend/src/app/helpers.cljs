(ns app.helpers)

(defn current-path []
  (.-pathname (.-location js/window)))
