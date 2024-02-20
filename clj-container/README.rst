Usage
-----

Build locally::

    $ podman build -t clj .

Use
---

Start closure terminal::

    $ podman run --rm -ti clj clj
    Downloading: org/clojure/clojure/1.11.1/clojure-1.11.1.pom from central
    Downloading: org/clojure/spec.alpha/0.3.218/spec.alpha-0.3.218.pom from central
    Downloading: org/clojure/core.specs.alpha/0.2.62/core.specs.alpha-0.2.62.pom from central
    Downloading: org/clojure/pom.contrib/1.1.0/pom.contrib-1.1.0.pom from central
    Downloading: org/clojure/core.specs.alpha/0.2.62/core.specs.alpha-0.2.62.jar from central
    Downloading: org/clojure/spec.alpha/0.3.218/spec.alpha-0.3.218.jar from central
    Downloading: org/clojure/clojure/1.11.1/clojure-1.11.1.jar from central
    Clojure 1.11.1
    user=>

Validate formating::

    $ podman run -v `pwd`:/tmp/workdir:z --rm -ti clj bash -c 'cd /tmp/workdir ; cljfmt check frontend/src'
