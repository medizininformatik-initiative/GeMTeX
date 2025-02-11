FROM maven:3.9.9-amazoncorretto-17 AS build
WORKDIR /app
COPY pom.xml .
COPY src ./src
COPY lib ./lib
COPY filters ./filters
RUN mvn clean package -DskipTests

FROM amazoncorretto:17
WORKDIR /inception_idlogik_recommender
COPY --from=build /app/target/id-logik-recommender.jar .
COPY --from=build /app/filters .

EXPOSE 8080

ENTRYPOINT ["java", "-jar", "id-logik-recommender.jar"]