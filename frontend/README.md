# Frontend

## Dependencies

This is not packaged, and probably never will be. Install dependencies
manually:

```
dnf install npm
```

## Development

```
npx shadow-cljs watch app
```

It will tell you to open the page at http://localhost:3000 , ignore
it. Instead, open whatever URL is served by Flask webserver. The
ClojureScript hot-reload will work.


## Linter

Check possible problems with the code:

```
npx shadow-cljs run clj-kondo.main/main --lint src
```

Check formatting issues:

```
npx shadow-cljs run cljfmt.main check
```

You can automatically format the code using

```
npx shadow-cljs run cljfmt.main fix
```
