(ns app.homepage-validation
  (:require
   [cljs.core.match :refer-macros [match]]))


(defn numeric? [string]
  (not (js/isNaN (js/Number string))))

(defn validate [current-hash-atom input-values input-errors]
  ;; This function works but the implementationo is disgusting and not at all
  ;; how it is supposed to be done. We can refactor in the future.
  (reset! input-errors [])
  (match @current-hash-atom
         "#copr"
         (do
           (when (empty? (get @input-values :copr-build-id))
             (swap! input-errors conj "copr-build-id"))

           (when (not (numeric? (get @input-values :copr-build-id)))
             (swap! input-errors conj "copr-build-id"))

           (when (empty? (get @input-values :copr-chroot))
             (swap! input-errors conj "copr-chroot")))

         "#packit"
         (do
           (when (empty? (get @input-values :packit-id))
             (swap! input-errors conj "packit-id"))

           (when (not (numeric? (get @input-values :packit-id)))
             (swap! input-errors conj "packit-id")))

         "#koji"
         (do
           (when (empty? (get @input-values :koji-build-id))
             (swap! input-errors conj "koji-build-id"))

           (when (not (numeric? (get @input-values :koji-build-id)))
             (swap! input-errors conj "koji-build-id"))

           (when (empty? (get @input-values :koji-arch))
             (swap! input-errors conj "koji-arch")))

         "#url"
         (do
           (when (empty? (get @input-values :url))
             (swap! input-errors conj "url")))))
