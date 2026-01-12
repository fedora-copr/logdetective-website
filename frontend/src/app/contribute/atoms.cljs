(ns app.contribute.atoms
  (:require [reagent.core :as r]))

(def spec (r/atom nil))
(def container (r/atom nil))
(def backend-data (r/atom nil))
(def log (r/atom nil))
(def build-id (r/atom nil))
(def build-id-title (r/atom nil))
(def build-url (r/atom nil))
(def text-in-log-selected? (r/atom nil))
(def ok-status (r/atom nil))
