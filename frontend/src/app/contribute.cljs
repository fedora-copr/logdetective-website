(ns app.contribute
  (:require [reagent.core :as r]
            [clojure.string :as str]
            [cljs.core.match :refer-macros [match]]
            [web.Range :refer [surround-contents]]))


(def log (r/atom (str/join "\n" [
"INFO: chroot_scan: 3 files copied to /var/lib/copr-rpmbuild/results/chroot_scan"
"INFO: /var/lib/mock/fedora-37-x86_64-1692181166.067366/root/var/log/dnf.rpm.log"
"/var/lib/mock/fedora-37-x86_64-1692181166.067366/root/var/log/dnf.librepo.log"
"/var/lib/mock/fedora-37-x86_64-1692181166.067366/root/var/log/dnf.log"
"ERROR:"
"Exception(/var/lib/copr-rpmbuild/results/copr-rpmbuild-0.69-1.fc37.src.rpm)"
"Config(fedora-37-x86_64) 0 minutes 28 seconds"
"INFO: Results and/or logs in: /var/lib/copr-rpmbuild/results"
"INFO: Cleaning up build root ('cleanup_on_failure=True')"
"Start: clean chroot"
"INFO: unmounting tmpfs."
"Finish: clean chroot"
"ERROR: Command failed:"
 "# /usr/bin/systemd-nspawn -q -M"
"15916d5fd0524fe090a40cbc09f15279 -D"
"/var/lib/mock/fedora-37-x86_64-bootstrap-1692181166.067366/root"
"-a --capability=cap_ipc_lock --rlimit=RLIMIT_NOFILE=10240"
"--capability=cap_ipc_lock"
"--bind=/tmp/mock-resolv.0pyv_f8p:/etc/resolv.conf"
"/var/lib/mock/fedora-37-x86_64-1692181166.067366/root/"
"--releasever 37 --setopt=deltarpm=False"
"--setopt=allow_vendor_change=yes --allowerasing"
"--disableplugin=local --disableplugin=spacewalk"
"--disableplugin=versionlock"
"/var/lib/mock/fedora-37-x86_64-1692181166.067366/root//builddir/build/SRPMS/"
"copr-rpmbuild-0.69-1.fc37.src.rpm"
"--setopt=tsflags=nocontexts --setopt=tsflags=nocontexts"
"--setopt=tsflags=nocontexts"
"No matches found for the following disable plugin patterns: local, spacewalk, versionlock"
"Copr repository                                  55 kB/s | 1.8 kB     00:00"
"fedora                                          299 kB/s |  26 kB     00:00"
"updates                                         403 kB/s |  19 kB     00:00"
"No matching package to install: 'python3-specfile >= 0.21.0'"
"Not all dependencies satisfied"
"Error: Some packages could not be found."
""
"Copr build error: Build failed"
])))


(def active-tab (r/atom "backend.log"))
(def snippets (r/atom nil))
(def files (r/atom nil))


(defn init-data []
  (reset!
   files
   [{:name "builder-live.log"
     :content nil}

    {:name "import.log"
     :content nil}

    {:name "backend.log"
     :content nil}

    {:name "root.log"
     :content nil}])

  ;; (reset!
  ;;  snippets
  ;;  ["There is an exception, so that's the error, right?"
  ;;   "The python3-specfile package was not available in 0.21.0 version or higher."
  ;;   "Third snippet"])

  )

(defn render-tab [name]
  (let [active? (= name @active-tab)]
    [:li {:class "nav-item" :key name}
     [:a {:class ["nav-link" (if active? "active" nil)]
          :on-click #(reset! active-tab name)
          :href "#"}
      name]]))

(defn render-tabs []
  [:ul {:class "nav nav-tabs"}
   (doall (for [file @files]
     (render-tab (:name file))))])

(defn render-left-column []
  [:div {:class "col-3"}
   [:h4 {} "Instructions"]
   [:ul {}
    [:li {}
     "We fetched logs for Copr build "
     [:a {:href "#"} "#123456"]]
    [:li {} "Write why do you think the build failed"]
    [:li {} "Find log snippets relevant to the failure"]
    [:li {} "Anotate snippets by selecting them, and clicking 'Anotate selection'"]
    [:li {} "Submit"]]])

(defn render-middle-column []
  [:div {:class "col-6"}
   (render-tabs)
   [:pre {:id "log" :dangerouslySetInnerHTML {:__html @log}}]])

(defn render-snippet [i snippet show?]
  [:div {:class "accordion-item" :key i}
   [:h2 {:class "accordion-header"}
    [:button
     {:class "accordion-button"
      :type "button"
      :data-bs-toggle "collapse"
      :data-bs-target (str "#snippetCollapse" i)
      :aria-controls (str "snippetCollapse" i)}
     (str "Snippet " (+ i 1))]]

   [:div {:id (str "snippetCollapse" i)
          :class ["accordion-collapse collapse" (if show? "show" nil)]
          :data-bs-parent "#accordionSnippets"}

    [:div {:class "accordion-body"}
     [:textarea
      {:class "form-control"
       :rows "3"
       :placeholder
       "What makes this snippet relevant?"}]
     [:div {}
      [:button {:type "button" :class "btn btn-outline-danger"} "Delete"]]]]])

(defn render-snippets []
   (doall (for [enumerated-snippet (map-indexed list @snippets)]
            (render-snippet (first enumerated-snippet)
                            (second enumerated-snippet)
                            (= (first enumerated-snippet)
                               (- (count @snippets) 1))))))

(defn highlight-current-snippet []
  ;; The implementation heavily relies on JavaScript interop. I took the
  ;; "Best Solution" code from:
  ;; https://itecnote.com/tecnote/javascript-selected-text-highlighting-prob/
  ;; and translated it from Javascript to ClojureScript using:
  ;; https://roman01la.github.io/javascript-to-clojurescript/
  (def rangee (.getRangeAt (.getSelection js/window) 0))
  (def span (.createElement js/document "span"))
  (set! (.-className span) "snippet")
  (.appendChild span (.extractContents rangee))
  (.insertNode rangee span))

(defn clear-selection []
  ;; Generated from
  ;; https://stackoverflow.com/a/13415236/3285282
  (cond
    (.-getSelection js/window) (.removeAllRanges (.getSelection js/window))
    (.-selection js/document) (.empty (.-selection js/document))
    :else nil))

(defn selection-node-id []
  (.-id (.-parentNode (.-baseNode (.getSelection js/window)))))

(defn add-snippet []
  (when (= (selection-node-id) "log")
    (highlight-current-snippet)
    (swap! snippets conj (.toString (.getSelection js/window)))
    (clear-selection)))

(defn render-right-column []
  [:div {:class "col-3" :id "right-column"}
   [:div {:class "mb-3"}
    [:label {:class "form-label"} "Copr build ID"]
    [:input {:type "text" :class "form-control" :value "123456"
             :disabled true :readOnly true}]]

   [:div {:class "mb-3"}
    [:label {:class "form-label"} "How to fix the issue?"]
    [:textarea {:class "form-control" :rows 3
                :placeholder (str "Please describe how to fix the issue in "
                                  "order for the build to succeed.")}]]

   [:label {:class "form-label"} "Interesting snippets:"]
   [:br]
   (when @snippets
     [:div {}
     [:button {:class "btn btn-secondary btn-lg" :on-click #(add-snippet)} "Add"]
     [:br]
     [:br]])

   (if @snippets
     [:div {:class "accordion" :id "accordionSnippets"}
      (render-snippets)]

     [:div {:class "card"}
      [:div {:class "card-body"}
       [:h5 {:class "card-title"} "No snippets yet"]
       [:p {:class "card-text"}
        (str "Please select interesting parts of the log files and press the "
             "'Add' button to annotate them")]
       [:button {:class "btn btn-secondary btn-lg"
                 :on-click #(add-snippet)}
        "Add"]]])

   [:div {:class "col-auto row-gap-3" :id "submit"}
    [:label {:class "form-label"} "Ready to submit the results?"]
    [:br]
    [:button {:type "submit" :class "btn btn-primary btn-lg"} "Submit"]]])

;; We might need this function for enabling/disabling the "new snippet" button
;; based on whether user selected something (within the <pre>log</pre> area)
;; (defn on-selection-change [event]
;;   (let [selection (js/window.getSelection)]
;;     (js/console.log selection)
;;     (js/console.log selection.anchorOffset)
;;     (js/console.log selection.focusOffset)))

(defn contribute []
  ;; I don't know why we need to do it this way,
  ;; instead of like :on-click is done
  ;; (js/document.addEventListener "selectionchange" on-selection-change)

  [:div {:class "row"}
   (render-left-column)
   (render-middle-column)
   (render-right-column)])
