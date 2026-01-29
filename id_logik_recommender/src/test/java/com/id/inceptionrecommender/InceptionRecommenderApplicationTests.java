package com.id.inceptionrecommender;

import com.id.inceptionrecommender.rest.AnnotationFilter;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.junit.jupiter.api.Assertions;

@SpringBootTest(useMainMethod = SpringBootTest.UseMainMethod.ALWAYS)
class InceptionRecommenderApplicationTests {

    @Autowired AnnotationFilter.AnnotationProperties annotationProperties;
    @Autowired AnnotationFilter filter;

    @Test
    void contextLoads() {
        Assertions.assertEquals(23, annotationProperties.getDomainFilterConcepts().split(";").length);
        Assertions.assertNotNull(annotationProperties.getFilterFile());
        Assertions.assertNotNull(filter.getFilterItems());
    }

}
