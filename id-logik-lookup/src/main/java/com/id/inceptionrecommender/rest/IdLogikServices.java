package com.id.inceptionrecommender.rest;

import com.id.idlogik.app.ResultItem;
import com.id.idlogik.app.Task;
import idlogik.IdLogikRestfulClient;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Component;

import java.util.List;
import java.util.Optional;

@Component
public class IdLogikServices {

    private final IdLogikRestfulClient idLogikRestfulClient;

    @Autowired
    public IdLogikServices(InceptionRecommender.IdLogikClientProperties config) {
        idLogikRestfulClient = new IdLogikRestfulClient(config.getProtocol(), config.getHost(), config.getPort());
        idLogikRestfulClient.setLicence(config.getLicence());
        idLogikRestfulClient.login();
    }

    @Cacheable(value = "snomedCTConcept", key = "#text")
    public Optional<String> text2SingleSCT(String text) {
        Task task = new Task();
        task.setServiceName("term.Index");
        task.getParameter().setProperty("SEARCHTEXT", text);
        task.getParameter().setProperty("NOMENCLATURE_IDX", "1");
        task.getParameter().setProperty("LANGUAGE", "0");
        task.getParameter().setProperty("COMPOSITIONAL", "1");
        task.getParameter().setProperty("USE_X_INDICES", "0");
        task.getParameter().setProperty("EXTRACTION_PROFILE", "SEARCH");
        idLogikRestfulClient.call(task);
        if (task.getResultItems().size() == 1) {
            return Optional.of(task.getResultItems().get(0).getAttributes().getProperty("NAME"));
        } else {
            return Optional.empty();
        }
    }

    @Cacheable(value = "text2FullSCT", key = "#text")
    public List<ResultItem> text2FullSCT(String text) {
        Task task = new Task();
        task.setServiceName("term.Index");
        task.getParameter().setProperty("SEARCHTEXT", text);
        task.getParameter().setProperty("NOMENCLATURE_IDX", "1");
        task.getParameter().setProperty("LANGUAGE", "0");
        task.getParameter().setProperty("COMPOSITIONAL", "1");
        task.getParameter().setProperty("USE_X_INDICES", "0");
        task.getParameter().setProperty("EXTRACTION_PROFILE", "SEARCH");
        idLogikRestfulClient.call(task);
        return task.getResultItems();
        /*
        if (task.getResultItems().size() == 1) {
            return Optional.of(task.getResultItems().get(0).getAttributes().getProperty("NAME"));
        } else {
            return Optional.empty();
        }
        */
    }

    public List<ResultItem> text2SCT(String text) {
        Task task = new Task();
        task.setServiceName("term.Index");
        task.getParameter().setProperty("SEARCHTEXT", text);
        task.getParameter().setProperty("NOMENCLATURE_IDX", "1");
        task.getParameter().setProperty("LANGUAGE", "0");
        task.getParameter().setProperty("COMPOSITIONAL", "1");
        task.getParameter().setProperty("USE_X_INDICES", "0");
        task.getParameter().setProperty("EXTRACTION_PROFILE", "SEARCH");
        idLogikRestfulClient.call(task);
        return task.getResultItems();
    }

    public List<ResultItem> findCoding(String content) {
        Task task = new Task();
        task.setServiceName("extraction.FindCoding");
        task.getParameter().setProperty("SEARCHTEXT", content);
        task.getParameter().setProperty("VERSION_IDX", "153");
        task.getParameter().setProperty("CLASS_IDX", "265");
        task.getParameter().setProperty("CONTEXT", "0");
        task.getParameter().setProperty("MAX_RESULT_LINES", "1");
        idLogikRestfulClient.call(task);
        return task.getResultItems();
    }

    public List<ResultItem> searchDiagnoses(String dx) {
        Task task = new Task();
        task.setServiceName("classification.SearchDiagnoses");
        task.getParameter().setProperty("SEARCHTEXT", dx);
        task.getParameter().setProperty("YEAR", "2023");
        task.getParameter().setProperty("COUNTRY", "DE");
        task.getParameter().setProperty("FORMAT", "%I%C?%T");
        idLogikRestfulClient.call(task);
        return task.getResultItems();
    }

    public List<ResultItem> lookUpICD10(String code) {
        Task task = new Task();
        task.setServiceName("term.GetConcept");
        task.getParameter().setProperty("IDENT_NR", code);
        idLogikRestfulClient.call(task);
        return task.getResultItems();
    }

    public List<ResultItem> lookupSCTConcept(String concept) {
        Task task = new Task();
        task.setServiceName("term.GetIndex");
        task.getParameter().setProperty("NAME", concept);
        task.getParameter().setProperty("NOMENCLATURE_IDX", "1");
        task.getParameter().setProperty("LANGUAGE", "0");
        task.getParameter().setProperty("TEXT_ONLY", "1");
        task.getParameter().setProperty("DETAIL_MODE", "0");
        idLogikRestfulClient.call(task);
        return task.getResultItems();
    }

}
