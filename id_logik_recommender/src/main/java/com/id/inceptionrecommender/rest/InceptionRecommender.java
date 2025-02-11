package com.id.inceptionrecommender.rest;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.id.idlogik.app.ResultItem;
import org.apache.uima.UIMAFramework;
import org.apache.uima.cas.CAS;
import org.apache.uima.cas.Feature;
import org.apache.uima.cas.SerialFormat;
import org.apache.uima.cas.Type;
import org.apache.uima.cas.text.AnnotationFS;
import org.apache.uima.fit.util.CasUtil;
import org.apache.uima.resource.metadata.TypeSystemDescription;
import org.apache.uima.util.CasCreationUtils;
import org.apache.uima.util.CasIOUtils;
import org.apache.uima.util.XMLInputSource;
import org.apache.uima.util.XMLParser;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;

import static org.apache.commons.lang3.StringUtils.isEmpty;
import static org.springframework.http.HttpStatus.OK;

@RestController
@RequestMapping("/inception")
public class InceptionRecommender {

  public static final String SCT_URL = "http://snomed.info/id/";
  IdLogikServices idLogikServices;
  AnnotationFilter annotationFilter;

  @Autowired
  public InceptionRecommender(IdLogikClientProperties config, IdLogikServices idLogikServices,
                              AnnotationFilter annotationFilter) {
    this.idLogikServices = idLogikServices;
    this.annotationFilter = annotationFilter;
  }

  @RequestMapping(value = "/recommender/predict", method = RequestMethod.POST)
  @ResponseBody
  public ResponseEntity<String> predict(@RequestBody String jsonDoc) throws Exception {
    //Extract information from requestBody
    ObjectMapper objectMapper = new ObjectMapper();
    JsonNode rootNode = objectMapper.readTree(jsonDoc);
    JsonNode typeSystem = rootNode.path("typeSystem");
    String typeSystemString = typeSystem.textValue();
    JsonNode xmiDoc = rootNode.path("document").path("xmi");
    String xmiDocString = xmiDoc.textValue();
    JsonNode metaData = rootNode.path("metadata");
    //prepare and execute transformation to CAS
    XMLParser xmlParser = UIMAFramework.getXMLParser();
    XMLInputSource xmlTypeSystemSource = new XMLInputSource(new ByteArrayInputStream(typeSystemString.getBytes(StandardCharsets.UTF_8)));
    TypeSystemDescription typeSystemDescriptor = (TypeSystemDescription) xmlParser.parse(xmlTypeSystemSource);
    CAS casDoc = CasCreationUtils.createCas(typeSystemDescriptor, null, null);
    CasIOUtils.load(new ByteArrayInputStream(xmiDocString.getBytes(StandardCharsets.UTF_8)), casDoc);
    //manipulate CAS
    final String content = casDoc.getDocumentText();
    final String layerID = metaData.get("layer").textValue();
    final String featureID = metaData.get("feature").textValue();

    Type annotationType = casDoc.getTypeSystem().getType(layerID);
    Feature feature = annotationType.getFeatureByBaseName(featureID);
    Feature inception_internal_predicted = annotationType.getFeatureByBaseName("inception_internal_predicted");

    for (com.id.idlogik.app.ResultItem r : idLogikServices.findCoding(content)) {
      AnnotationFS annotation = casDoc.createAnnotation(
              annotationType,
              Integer.parseInt(r.getAttributes().getProperty("ATTR_LEFT")),
              Integer.parseInt(r.getAttributes().getProperty("ATTR_RIGHT")));
      if (!r.getSubElements().isEmpty()) {
        annotation.setFeatureValueFromString(feature, r.getSubElements().get(0).getValueString().replaceAll("[|]", ","));
      } else {
        annotation.setFeatureValueFromString(feature, r.getAttributes().getProperty("STATUS", r.getValueString()));
      }
      annotation.setFeatureValueFromString(inception_internal_predicted, "true");
      casDoc.addFsToIndexes(annotation);
    }

    //transform back to XMI/XML/JSON
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    CasIOUtils.save(casDoc, out, SerialFormat.XMI);
    rootNode = objectMapper.createObjectNode();
    xmiDoc = ((ObjectNode) rootNode).put("document", out.toString());
    out.reset();
    objectMapper.writeValue(out, xmiDoc);
    return new ResponseEntity<>(out.toString(), OK);
  }

  @RequestMapping(value = "/annotate/train", method = RequestMethod.POST)
  public void train(@RequestBody String jsonDoc) throws Exception {
    //no implementation, just avoid error message in inception
  }

  @RequestMapping(value = {"/annotate/predict"}, method = RequestMethod.POST)
  @ResponseBody
  public ResponseEntity<String> annotate(@RequestBody String jsonDoc) throws Exception {
    //Extract information from requestBody
    ObjectMapper objectMapper = new ObjectMapper();
    JsonNode rootNode = objectMapper.readTree(jsonDoc);
    JsonNode typeSystem = rootNode.path("typeSystem");
    String typeSystemString = typeSystem.textValue();
    JsonNode xmiDoc = rootNode.path("document").path("xmi");
    String xmiDocString = xmiDoc.textValue();
    JsonNode metaData = rootNode.path("metadata");
    //prepare and execute transformation to CAS
    XMLParser xmlParser = UIMAFramework.getXMLParser();
    XMLInputSource xmlTypeSystemSource = new XMLInputSource(new ByteArrayInputStream(typeSystemString.getBytes(StandardCharsets.UTF_8)));
    TypeSystemDescription typeSystemDescriptor = (TypeSystemDescription) xmlParser.parse(xmlTypeSystemSource);
    CAS casDoc = CasCreationUtils.createCas(typeSystemDescriptor, null, null);
    CasIOUtils.load(new ByteArrayInputStream(xmiDocString.getBytes(StandardCharsets.UTF_8)), casDoc);
    //manipulate CAS
    final String content = casDoc.getDocumentText();
    final String layerID = metaData.get("layer").textValue();
    final String featureID = metaData.get("feature").textValue();
    Type annotationType = casDoc.getTypeSystem().getType(layerID);
    Feature feature = annotationType.getFeatureByBaseName(featureID);
    Feature inception_internal_predicted = annotationType.getFeatureByBaseName("inception_internal_predicted");
    Feature id_score_explanation = annotationType.getFeatureByBaseName("id_score_explanation");

    for (AnnotationFS annotationFS : CasUtil.select(casDoc, annotationType)) {
      for (ResultItem ri : idLogikServices.text2FullSCT(annotationFilter.filter(annotationFS.getCoveredText()))) {
        final String sctConcept = ri.getAttributes().getProperty("NAME");
        final String sctLabel = ri.getAttributes().getProperty("TXT");
        //Don't use concepts starting with "X" - these are internal concepts that mark suggestions
        if (!sctConcept.startsWith("X")) {
          AnnotationFS annotation = casDoc.createAnnotation(
                  annotationType, annotationFS.getBegin(), annotationFS.getEnd()
          );
                                                                         //remove negation marker
          annotation.setFeatureValueFromString(feature, SCT_URL.concat(sctConcept.replace("!", "")));
          annotation.setFeatureValueFromString(id_score_explanation, sctLabel);
          annotation.setFeatureValueFromString(inception_internal_predicted, Boolean.toString(true));
          casDoc.addFsToIndexes(annotation);
        }
      }
    }

    //transform back to XMI/XML/JSON
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    CasIOUtils.save(casDoc, out, SerialFormat.XMI);
    rootNode = objectMapper.createObjectNode();
    xmiDoc = ((ObjectNode) rootNode).put("document", out.toString());
    out.reset();
    objectMapper.writeValue(out, xmiDoc);
    return new ResponseEntity<>(out.toString(), OK);
  }


  @RequestMapping(value = "/lookup_sct", method = RequestMethod.GET)
  public String lookup_sct(String q, String qc, Integer l, String id) throws Exception {
    ObjectMapper objectMapper = new ObjectMapper();
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    if (isEmpty(id)) {
      ArrayNode rootNode = objectMapper.createArrayNode();
      for (ResultItem r : idLogikServices.text2SCT(isEmpty(q)?qc:q)) {
        rootNode.add(objectMapper.createObjectNode()
                .put("id", r.getAttributes().getProperty("NAME"))
                .put("l", r.getAttributes().getProperty("NAME"))
                .put("d", r.getAttributes().getProperty("TXT")));
      }
      objectMapper.writeValue(out, rootNode);
    } else {
      ObjectNode rootNode = objectMapper.createObjectNode();
      java.util.List<ResultItem> res = idLogikServices.lookupSCTConcept(id);
      if (res.size() == 1) {
        rootNode
                .put("id", id)
                .put("l", id)
                .put("d", res.get(0).getValueString());
      }
      objectMapper.writeValue(out, rootNode);
    }
    return out.toString();
  }

  @RequestMapping(value = "/lookup_icd10", method = RequestMethod.GET)
  public String lookup_icd10(String q, String qc, Integer l, String id) throws Exception {
    ObjectMapper objectMapper = new ObjectMapper();
    ByteArrayOutputStream out = new ByteArrayOutputStream();
    if (isEmpty(id)) {
      ArrayNode rootNode = objectMapper.createArrayNode();
      for (ResultItem r : idLogikServices.searchDiagnoses(isEmpty(q)?qc:q)) {
        final String value = r.getValueString();
        if (!value.equals("-")) {
          final String[] valueParts = value.split("[|]");
          rootNode.add(objectMapper.createObjectNode()
                  .put("id", valueParts.length>0?valueParts[0]:"")
                  .put("l", valueParts.length>1?valueParts[1]:"")
                  .put("d", valueParts.length>2?valueParts[2]:""));
        }
      }
      objectMapper.writeValue(out, rootNode);

    } else {
      ObjectNode rootNode = objectMapper.createObjectNode();
      java.util.List<ResultItem> res = idLogikServices.lookUpICD10(id);
      if (res.size() == 1) {
        /*
        ResultItem: =|OID:(0:0-136901#7076348, 119)|ID:084646|ID_DIMDI:d14757|T0:Myopie|T1:Myopia|T4:myopie|T5:Миопия|T6:Krótkowzroczność|T8:Myopia|T9:Miopia|T11:MIOPIA|CTX:0|PA:0|WH:0|CAT:5|CAT_BGS:3^5^5^3|HVF1:36|HVF2:0|COD0;0:H52.1|COD12;0:H52.1|COD13;0:H52.1|COD14;0:367.1|COD16;0:H52.1|COD22;0:H52.1|COD24;0:99|COD25;0:055|COD30;0:H52.1|COD37;0:H52.1|COD48;0:H52.1|COD51;0:367.1|COD58;0:H52.1|COD61;0:H52.1|COD63;0:367.1|COD69;0:H52.1|COD72;0:H52.1|COD91;0:H52.1|COD93;0:367.1|COD105;0:H52.1|COD107;0:H52.1|COD110;0:367.1|COD118;0:H52.1|COD123;0:367.1|COD131;0:H52.1|COD140;0:367.1|COD153;0:H52.1|COD155;0:H52.1|COD164;0:H52.1|COD166;0:H52.1|COD175;0:H52.1|COD176;0:H52.1|COD179;0:H52.1|COD187;0:H52.1|COD189;0:H52.1|COD197;0:H52.1|COD199;0:H52.1|COD208;0:H52.1|COD209;0:H52.1|COD217;0:H52.1|COD220;0:H52.1|COD229;0:H52.1|COD230;0:H52.1|COD239;0:H52.1|COD241;0:H52.1|COD253;0:H52.1|COD255;0:H52.1|COD265;0:H52.1|COD267;0:H52.1|COD279;0:H52.1|CSB:0|WNC:F001450 X001814 X001851 F00016D E000008 D001F86 E0038C6 F000006 F001075 F002985 GA000C1|SN:TAA000FA0630|AGE:0;0|SEX:0|NT:|BL:-6626765238181990399^594556515344449824^2884978117561028616^-6916824927580258144^8391168|TNM:|ICDO:|UNIT0:0;0.0;0;0.0;0|UNIT12:0;0.0;0;0.0;0|UNIT13:0;0.0;0;0.0;0|UNIT14:0;0.0;0;0.0;0|UNIT16:0;0.0;0;0.0;0|UNIT22:0;0.0;0;0.0;0|UNIT24:0;0.0;0;0.0;0|UNIT25:0;0.0;0;0.0;0|UNIT30:0;0.0;0;0.0;0|UNIT37:0;0.0;0;0.0;0|UNIT48:0;0.0;0;0.0;0|UNIT51:0;0.0;0;0.0;0|UNIT58:0;0.0;0;0.0;0|UNIT61:0;0.0;0;0.0;0|UNIT63:0;0.0;0;0.0;0|UNIT69:0;0.0;0;0.0;0|UNIT72:0;0.0;0;0.0;0|UNIT91:0;0.0;0;0.0;0|UNIT93:0;0.0;0;0.0;0|UNIT105:0;0.0;0;0.0;0|UNIT107:0;0.0;0;0.0;0|UNIT110:0;0.0;0;0.0;0|UNIT118:0;0.0;0;0.0;0|UNIT123:0;0.0;0;0.0;0|UNIT131:0;0.0;0;0.0;0|UNIT140:0;0.0;0;0.0;0|UNIT153:0;0.0;0;0.0;0|UNIT155:0;0.0;0;0.0;0|UNIT164:0;0.0;0;0.0;0|UNIT166:0;0.0;0;0.0;0|UNIT175:0;0.0;0;0.0;0|UNIT176:0;0.0;0;0.0;0|UNIT179:0;0.0;0;0.0;0|UNIT187:0;0.0;0;0.0;0|UNIT189:0;0.0;0;0.0;0|UNIT197:0;0.0;0;0.0;0|UNIT199:0;0.0;0;0.0;0|UNIT208:0;0.0;0;0.0;0|UNIT209:0;0.0;0;0.0;0|UNIT217:0;0.0;0;0.0;0|UNIT220:0;0.0;0;0.0;0|UNIT229:0;0.0;0;0.0;0|UNIT230:0;0.0;0;0.0;0|UNIT239:0;0.0;0;0.0;0|UNIT241:0;0.0;0;0.0;0|UNIT253:0;0.0;0;0.0;0|UNIT255:0;0.0;0;0.0;0|UNIT265:0;0.0;0;0.0;0|UNIT267:0;0.0;0;0.0;0|UNIT279:0;0.0;0;0.0;0|SI:3|MP:-1|SMB:0¤0¤-1¤0¤0¤=0¤1¤0¤0¤0¤3¤3¤0¤0¤0¤0¤0¤0¤0¤=0¤0¤0¤0|DKR:|DKR_PSYCH:|FOKA_KDE:|SEG4:|FOKA_KDA:|IDH:-1|MEL:|ASK:|INFO:8|AC:3
         */
        String identNr = "";
        String code = "";
        String text = "";
        final String[] valueParts = res.get(0).getValueString().split("[|]");
        for (String valuePart : valueParts) {
          if (valuePart.startsWith("T0:"))
            text = valuePart.split("[:]")[1];
          if (valuePart.startsWith("ID:"))
            identNr = valuePart.split("[:]")[1];
          if (valuePart.startsWith("COD253;0:"))
            code = valuePart.split("[:]")[1];
        }
        rootNode
                .put("id", identNr)
                .put("l", code)
                .put("d", text);
      }

      objectMapper.writeValue(out, rootNode);
    }
    return out.toString();
  }

  @Configuration
  @ConfigurationProperties(prefix = "idlogik")
  public static class IdLogikClientProperties {

    private String protocol;
    private String host;
    private int port;
    private String licence;

    public String getProtocol() {
      return protocol;
    }

    public void setProtocol(String protocol) {
      this.protocol = protocol;
    }

    public String getHost() {
      return host;
    }

    public void setHost(String host) {
      this.host = host;
    }

    public int getPort() {
      return port;
    }

    public void setPort(int port) {
      this.port = port;
    }

    public String getLicence() {
      return licence;
    }

    public void setLicence(String licence) {
      this.licence = licence;
    }

  }
}
