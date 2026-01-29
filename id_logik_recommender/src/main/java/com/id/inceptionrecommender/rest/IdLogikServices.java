package com.id.inceptionrecommender.rest;

import com.id.idlogik.app.ResultItem;
import com.id.idlogik.app.Task;
import com.id.shared.Sleep;
import idlogik.IdLogikRestfulClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

@Component
public class IdLogikServices {

    public static final String SESSION_ID = "SESSION_ID";
    public static final String SEARCHTEXT = "SEARCHTEXT";
    public static final String NOMENCLATURE_IDX = "NOMENCLATURE_IDX";
    public static final String LANGUAGE = "LANGUAGE";
    public static final String COMPOSITIONAL = "COMPOSITIONAL";
    public static final String USE_X_INDICES = "USE_X_INDICES";
    public static final String EXTRACTION_PROFILE = "EXTRACTION_PROFILE";
    public static final String FILTER_NAME = "FILTER_NAME";
    public static final String VERSION_IDX = "VERSION_IDX";
    public static final String CLASS_IDX = "CLASS_IDX";
    public static final String CONTEXT = "CONTEXT";
    public static final String MAX_RESULT_LINES = "MAX_RESULT_LINES";
    public static final String YEAR = "YEAR";
    public static final String COUNTRY = "COUNTRY";
    public static final String FORMAT = "FORMAT";
    public static final String NAME = "NAME";
    public static final String TEXT_ONLY = "TEXT_ONLY";
    public static final String DETAIL_MODE = "DETAIL_MODE";

    public static final String TERM_INDEX = "term.Index";
    public static final String EXTRACTION_FIND_CODING = "extraction.FindCoding";
    public static final String CLASSIFICATION_SEARCH_DIAGNOSES = "classification.SearchDiagnoses";
    public static final String TERM_GET_CONCEPT = "term.GetConcept";
    public static final String TERM_GET_INDEX = "term.GetIndex";
    public static final String SEARCH = "SEARCH";

    private final IdLogikRestfulClient idLogikRestfulClient;
    private final AnnotationFilter.AnnotationProperties annotationProperties;

    @Autowired
    public IdLogikServices(InceptionRecommender.IdLogikClientProperties config, AnnotationFilter.AnnotationProperties annotationProperties) {
        idLogikRestfulClient = new IdLogikRestfulClient(config.getProtocol(), config.getHost(), config.getPort());
        idLogikRestfulClient.setLicence(config.getLicence());
        idLogikRestfulClient.login();
        idLogikRestfulClient.setAutoLogin(true);
        idLogikRestfulClient.setRetryAtNoSessionID(true);
        idLogikRestfulClient.setMaxReconnect(10);
        this.annotationProperties = annotationProperties;
    }

    protected void call(Task task) {
        call(task, 10);
    }

    /*
     Diese Methode prüft, ob die Session-ID noch gültig ist und invalidiert diese ggf.
     Es werden maximal 10 Versuche durchgeführt, wobei jeweils fünf Sekunden Wartezeit dazwischen liegt
     (falls der ID LOGIK Server gerade startet)
     */
    protected void call(Task task, int retries) {
        final int status = idLogikRestfulClient.call(task);
        if (retries > 0 && status == 1008) {
            task.getParameter().remove(SESSION_ID);
            idLogikRestfulClient.setSessionID("");
            Sleep.doSleep(5000);
            call(task, retries-1);
        }
    }

    @Cacheable(value = "SCT_ANNO_CACHE", key = "#text", unless="#result.size()==0")
    public List<ResultItem> text2FullSCT(String text) {
        Task task = new Task();
        task.setServiceName(TERM_INDEX);
        task.getParameter().setProperty(SEARCHTEXT, text);
        task.getParameter().setProperty(NOMENCLATURE_IDX, "1");
        task.getParameter().setProperty(LANGUAGE, "0");
        task.getParameter().setProperty(COMPOSITIONAL, "1");
        task.getParameter().setProperty(USE_X_INDICES, "0");
        task.getParameter().setProperty(EXTRACTION_PROFILE, SEARCH);
        call(task);
        return task.getResultItems();
    }

    public List<ResultItem> text2SCT(String text) {
        Task task = new Task();
        task.setServiceName(TERM_INDEX);
        task.getParameter().setProperty(SEARCHTEXT, text);
        task.getParameter().setProperty(NOMENCLATURE_IDX, "1");
        task.getParameter().setProperty(LANGUAGE, "0");
        task.getParameter().setProperty(COMPOSITIONAL, "1");
        task.getParameter().setProperty(USE_X_INDICES, "0");
        task.getParameter().setProperty(EXTRACTION_PROFILE, SEARCH);
        //First, determine concepts that should be filtered out
        task.getParameter().setProperty(FILTER_NAME, annotationProperties.getDomainFilterConcepts());
        call(task);
        //Copy these concepts
        List<ResultItem> filtered = new ArrayList<>(task.getResultItems());
        //Now get all concepts
        task.getParameter().remove(FILTER_NAME);
        task.getResultItems().clear();
        call(task);
        //And remove filtered concepts
        task.getResultItems().removeIf(filtered::contains);
        return task.getResultItems();
    }

    public List<ResultItem> findCoding(String content) {
        Task task = new Task();
        task.setServiceName(EXTRACTION_FIND_CODING);
        task.getParameter().setProperty(SEARCHTEXT, content);
        task.getParameter().setProperty(VERSION_IDX, "153");
        task.getParameter().setProperty(CLASS_IDX, "265");
        task.getParameter().setProperty(CONTEXT, "0");
        task.getParameter().setProperty(MAX_RESULT_LINES, "1");
        call(task);
        return task.getResultItems();
    }

    public List<ResultItem> searchDiagnoses(String dx) {
        Task task = new Task();
        task.setServiceName(CLASSIFICATION_SEARCH_DIAGNOSES);
        task.getParameter().setProperty(SEARCHTEXT, dx);
        task.getParameter().setProperty(YEAR, "2023");
        task.getParameter().setProperty(COUNTRY, "DE");
        task.getParameter().setProperty(FORMAT, "%I%C?%T");
        call(task);
        return task.getResultItems();
    }

    public List<ResultItem> lookUpICD10(String code) {
        Task task = new Task();
        task.setServiceName(TERM_GET_CONCEPT);
        task.getParameter().setProperty("IDENT_NR", code);
        call(task);
        return task.getResultItems();
    }

    public List<ResultItem> lookupSCTConcept(String concept) {
        Task task = new Task();
        task.setServiceName(TERM_GET_INDEX);
        task.getParameter().setProperty(NAME, concept);
        task.getParameter().setProperty(NOMENCLATURE_IDX, "1");
        task.getParameter().setProperty(LANGUAGE, "0");
        task.getParameter().setProperty(TEXT_ONLY, "1");
        task.getParameter().setProperty(DETAIL_MODE, "0");
        call(task);
        return task.getResultItems();
    }

    public Optional<String> text2SingleSCT(String text) {
        Task task = new Task();
        task.setServiceName(TERM_INDEX);
        task.getParameter().setProperty(SEARCHTEXT, text);
        task.getParameter().setProperty(NOMENCLATURE_IDX, "1");
        task.getParameter().setProperty(LANGUAGE, "0");
        task.getParameter().setProperty(COMPOSITIONAL, "1");
        task.getParameter().setProperty(USE_X_INDICES, "0");
        task.getParameter().setProperty(EXTRACTION_PROFILE, SEARCH);
        call(task);
        if (task.getResultItems().size() == 1) {
            return Optional.of(task.getResultItems().get(0).getAttributes().getProperty("NAME"));
        } else {
            return Optional.empty();
        }
    }

}
