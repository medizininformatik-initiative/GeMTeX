package com.id.inceptionrecommender.rest;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Service;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.List;

    @Service
    public class AnnotationFilter {

        private List<String> filterItems;

        public AnnotationFilter(AnnotationProperties config) {
            try {
                filterItems = Files.readAllLines(Paths.get(config.getFilterFile()));
            } catch (IOException e) {
                e.printStackTrace();
            }
        }

        public List<String> getFilterItems() {
            return filterItems;
        }

        public String filter(String item) {
            for (String filterItem : filterItems) {
                item = item.replaceAll(filterItem, "");
                if (item.isEmpty()) return "";
            }
            return item;
        }

        @Configuration
        @ConfigurationProperties(prefix = "annotation")
        public static class AnnotationProperties {

            private String filterFile;
            private String domainFilterConcepts;

            public void setFilterFile(String filterFile) {
                this.filterFile = filterFile;
            }

            public String getFilterFile() {

                return filterFile;
            }

            public String getDomainFilterConcepts() {
                return domainFilterConcepts;
            }

        }
    }


