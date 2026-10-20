<!-- robot explain, HermiT, ROBOT 1.9.10, 2026-10-19: tr-extension-v0.ttl with only its import changed to the corrected Linked GTFS. Ferry trip is no longer impossible; Single-route stop still is, and only the domain of gtfs:route is left in its explanation. -->

## [Single-route stop](https://ul.edu.lb/kr/transit#SingleRouteStop) SubClassOf [Nothing](http://www.w3.org/2002/07/owl#Nothing) ##

  - [Single-route stop](https://ul.edu.lb/kr/transit#SingleRouteStop) SubClassOf [Route](http://vocab.gtfs.org/terms#route) exactly 1 [Ruta](http://vocab.gtfs.org/terms#Route)
    - [Route](http://vocab.gtfs.org/terms#route) Domain [Trip](http://vocab.gtfs.org/terms#Trip)
  - [Single-route stop](https://ul.edu.lb/kr/transit#SingleRouteStop) SubClassOf [Parada](http://vocab.gtfs.org/terms#Stop)
  -  DisjointClasses: [Empresa](http://vocab.gtfs.org/terms#Agency), [Regla tarifaria](http://vocab.gtfs.org/terms#FareRule), [GTFS Feed](http://vocab.gtfs.org/terms#Feed), [Ruta](http://vocab.gtfs.org/terms#Route), [Servicio](http://vocab.gtfs.org/terms#Service), [Service rule](http://vocab.gtfs.org/terms#ServiceRule), [forma del recorrido, trayecto, itinerario](http://vocab.gtfs.org/terms#Shape), [Station](http://vocab.gtfs.org/terms#Station), [Parada](http://vocab.gtfs.org/terms#Stop), [Stop time](http://vocab.gtfs.org/terms#StopTime), [Trip](http://vocab.gtfs.org/terms#Trip)

