package com.id.inceptionrecommender.rest;

import com.id.idlogik.app.ResultItem;
import com.id.idlogik.app.Task;
import com.id.shared.Sleep;
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
        idLogikRestfulClient.setAutoLogin(true);
        idLogikRestfulClient.setRetryAtNoSessionID(true);
        idLogikRestfulClient.setMaxReconnect(10);
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
            task.getParameter().remove("SESSION_ID");
            idLogikRestfulClient.setSessionID("");
            Sleep.doSleep(5000);
            call(task, retries-1);
        }
    }

    @Cacheable(value = "SCT_ANNO_CACHE", key = "#text", unless="#task.getResultItems().size()==0")
    public List<ResultItem> text2FullSCT(String text) {
        Task task = new Task();
        task.setServiceName("term.Index");
        task.getParameter().setProperty("SEARCHTEXT", text);
        task.getParameter().setProperty("NOMENCLATURE_IDX", "1");
        task.getParameter().setProperty("LANGUAGE", "0");
        task.getParameter().setProperty("COMPOSITIONAL", "1");
        task.getParameter().setProperty("USE_X_INDICES", "0");
        task.getParameter().setProperty("EXTRACTION_PROFILE", "SEARCH");
        call(task);
        return task.getResultItems();
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
        call(task);
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
        call(task);
        return task.getResultItems();
    }

    public List<ResultItem> searchDiagnoses(String dx) {
        Task task = new Task();
        task.setServiceName("classification.SearchDiagnoses");
        task.getParameter().setProperty("SEARCHTEXT", dx);
        task.getParameter().setProperty("YEAR", "2023");
        task.getParameter().setProperty("COUNTRY", "DE");
        task.getParameter().setProperty("FORMAT", "%I%C?%T");
        call(task);
        return task.getResultItems();
    }

    public List<ResultItem> lookUpICD10(String code) {
        Task task = new Task();
        task.setServiceName("term.GetConcept");
        task.getParameter().setProperty("IDENT_NR", code);
        call(task);
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
        call(task);
        return task.getResultItems();
    }

    public Optional<String> text2SingleSCT(String text) {
        Task task = new Task();
        task.setServiceName("term.Index");
        task.getParameter().setProperty("SEARCHTEXT", text);
        task.getParameter().setProperty("NOMENCLATURE_IDX", "1");
        task.getParameter().setProperty("LANGUAGE", "0");
        task.getParameter().setProperty("COMPOSITIONAL", "1");
        task.getParameter().setProperty("USE_X_INDICES", "0");
        task.getParameter().setProperty("EXTRACTION_PROFILE", "SEARCH");
        call(task);
        if (task.getResultItems().size() == 1) {
            return Optional.of(task.getResultItems().get(0).getAttributes().getProperty("NAME"));
        } else {
            return Optional.empty();
        }
    }

}
