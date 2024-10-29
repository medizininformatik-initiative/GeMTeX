package idlogik;

import com.id.idlogik.app.IDLOGIK;
import com.id.idlogik.app.ResultItem;
import com.id.idlogik.app.Task;
import org.apache.commons.io.IOUtils;
import org.apache.http.NameValuePair;
import org.apache.http.message.BasicNameValuePair;
import org.apache.log4j.Logger;
import org.apache.xml.serialize.OutputFormat;
import org.apache.xml.serialize.XMLSerializer;
import org.w3c.dom.Document;
import org.w3c.dom.Element;
import org.w3c.dom.NodeList;
import org.xml.sax.InputSource;
import org.xml.sax.SAXException;

import javax.xml.bind.JAXBContext;
import javax.xml.bind.JAXBException;
import javax.xml.bind.Unmarshaller;
import javax.xml.bind.annotation.*;
import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import javax.xml.parsers.ParserConfigurationException;
import javax.xml.transform.*;
import javax.xml.transform.dom.DOMSource;
import javax.xml.transform.stream.StreamResult;
import java.io.*;
import java.net.URLEncoder;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/**
 * Utils for calling restful ID LOGIK web services.
 *
 * @author th
 */
@SuppressWarnings("restriction")
public final class IdLogikRestUtils {

  /**
   * Encoding
   */
  private static final String ENCODING_UTF_8 = "UTF-8";

  /**
   * Logging
   */
  private static final Logger LOGGER = Logger.getLogger(IdLogikRestUtils.class);

  /**
   * No instance
   */
  private IdLogikRestUtils() {
    // Util
  }

  /**
   * Creates a URL for calling an ID LOGIK Service
   *
   * @param host Host
   * @param port port
   * @param task Task to serialize
   * @return URL
   */
  public static String toGetUrl(String host, int port, Task task) {
    return toGetUrl(host, port, task, true);
  }


  /**
   * Creates a URL for calling an ID LOGIK Service
   *
   * @param host   Host
   * @param port   port
   * @param task   Task to serialize
   * @param encode Encode some chars
   * @return URL
   */
  public static String toGetUrl(String host, int port, Task task, boolean encode) {
    // URL-Anfang
    StringBuilder sb = new StringBuilder();
    sb.append("http://");
    sb.append(host);
    sb.append(":");
    sb.append(port);
    sb.append("/axis2/services/IDLOGIK/call?serviceName=");
    sb.append(task.getServiceName());
    sb.append("&");
    sb.append("parameter=");

    DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
    DocumentBuilder builder;
    try {
      // Parameter-XML via DOM bauen
      builder = factory.newDocumentBuilder();
      Document document = builder.newDocument();
      Element parameters = document.createElement("PARAMETERS");
      document.appendChild(parameters);
      for (Map.Entry entry : task.getParameter().entrySet()) {
        String key = (String) entry.getKey();
        String value = (String) entry.getValue();
        Element parameter = document.createElement("PARAMETER");
        parameters.appendChild(parameter);
        parameter.setAttribute("Name", key);
        parameter.setAttribute("Value", value);
      }
      // Jetzt als String umwandeln
      Source source = new DOMSource(document);
      StringWriter stringWriter = new StringWriter();
      Result result = new StreamResult(stringWriter);
      TransformerFactory tf = TransformerFactory.newInstance();
      Transformer transformer = tf.newTransformer();
      transformer.setOutputProperty("omit-xml-declaration", "yes");
      transformer.transform(source, result);
      String xmlAsString = stringWriter.getBuffer().toString();
      sb.append(encode ? URLEncoder.encode(xmlAsString, "UTF-8"/*StandardCharsets.UTF_8*/).replaceAll(Pattern.quote("+"), "%20") : xmlAsString);
      return sb.toString();

    } catch (ParserConfigurationException | TransformerException | UnsupportedEncodingException e) {
      throw new IllegalStateException("Error occurred", e);
    }
  }

  /**
   * Creates a URL for calling an ID LOGIK Service
   *
   * @param host           Host
   * @param port           port
   * @param task           Task to serialize
   * @param postParameters Post parameters
   * @return URL
   */
  public static String toPostUrl(String protocol, String host, int port, Task task, List<NameValuePair> postParameters) {
    // URL-Anfang
    StringBuilder sb = new StringBuilder();
    sb.append(protocol+"://");
    sb.append(host);
    sb.append(":");
    sb.append(port);
    sb.append("/axis2/idlogikrest?serviceName=");
    sb.append(task.getServiceName());

    for (Map.Entry entry : task.getParameter().entrySet()) {
      String key = entry.getKey().toString();
      String value = entry.getValue().toString();
      postParameters.add(
              new BasicNameValuePair(key, value));
    }

    return sb.toString();
  }

  /**
   * Serializes a {@link Element} instance into a string.
   *
   * @param element Element, must not be null.
   * @return String representation of the specified element.
   */
  public static String toString(Element element) {
    final StringWriter stringWriter = new StringWriter();
    final OutputFormat outputFormat = new OutputFormat((String) null, ENCODING_UTF_8, true);
    outputFormat.setLineWidth(200);
    outputFormat.setOmitXMLDeclaration(true);
    final BufferedWriter writer = new BufferedWriter(stringWriter);
    final XMLSerializer xmlSerializer = new XMLSerializer(writer, outputFormat);
    try {
      xmlSerializer.serialize(element);
    } catch (IOException e) {
    }
    return stringWriter.toString();
  }

  /**
   * Appends result items from restful web service response to a {@link Task}
   * instance.
   *
   * @param task        Task
   * @param inputStream InputSteam instance with XML response of web service.
   */
  public static void createResultItemsFromRestCall(Task task, InputStream inputStream) {
    String theString = null;
    try {
      DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
      DocumentBuilder builder = factory.newDocumentBuilder();
      StringWriter writer = new StringWriter();
      IOUtils.copy(inputStream, writer, "UTF-8");
      theString = writer.toString();
      Document document = builder.parse(new InputSource(new StringReader(theString)));
      NodeList nodeList = document.getElementsByTagName("idws:RESULT");
      if (nodeList != null && nodeList.getLength() == 1) {
        Element result = (Element) nodeList.item(0);

        JAXBContext jaxbContext = JAXBContext.newInstance(XmlResult.class);
        Unmarshaller unmarshaller = jaxbContext.createUnmarshaller();
        XmlResult xmlResult = (XmlResult) unmarshaller.unmarshal(result);
        XmlStatus status = xmlResult.getStatus();
        if (status != null && status.getValue() != null) {
          task.setStatus(status.getValue());
        } else {
          LOGGER.error("IDLOGIK-REST: No valid status in http response.");
          task.setStatus(IDLOGIK.IDLOGIK_ERROR_INTERNAL_IAE);
          return;
        }

        addResultItems(task, xmlResult.getResultItems());

      } else {
        LOGGER.error("IDLOGIK-REST: No RESULT-Element found in http response.");
        task.setStatus(IDLOGIK.IDLOGIK_ERROR_INTERNAL_IAE);
        return;
      }
    } catch (ParserConfigurationException e) {
      LOGGER.error("XML parser configuration exception", e);
    } catch (SAXException e) {
      LOGGER.error("SAX exception: " + theString, e);
    } catch (IOException e) {
      LOGGER.error("IO exception", e);
    } catch (JAXBException e) {
      LOGGER.error("JAXB exception", e);
    } catch (ClassCastException e) {
      LOGGER.error("Class cast exception: XML = " + theString, e);
    }

  }

  private static void addResultItems(Task task, List<XmlResultItem> resultItems) {
    if (resultItems == null)
      return;
    for (XmlResultItem resultItem : resultItems) {
      ResultItem item = convertToResultItem(resultItem);
      task.addResultItem(item);
    }
  }

  private static ResultItem convertToResultItem(XmlResultItem resultItem) {
    ResultItem result = new ResultItem();
    result.setName(resultItem.getName());
    result.setValue(resultItem.getValue());
    final List<XmlResultAttribute> attributes = resultItem.getAttributes();
    if (attributes != null) {
      for (XmlResultAttribute attribute : attributes) {
        if (attribute.getName() != null && attribute.getValue() != null) {
          result.getAttributes().setProperty(attribute.getName(), attribute.getValue());
        }
      }
    }
    final List<XmlResultItem> items = resultItem.getItems();
    if (items != null) {
      for (XmlResultItem item : items) {
        ResultItem subItem = convertToResultItem(item);
        result.addSubElement(subItem);
      }
    }
    return result;
  }

  @XmlAccessorType(XmlAccessType.FIELD)
  @XmlType(name = "")
  @XmlRootElement(name = "idws:ATTRIBUTE")
  public static class XmlResultAttribute {

    @XmlAttribute(name = "Name")
    private String name;

    @XmlAttribute(name = "Value")
    private String value;

    /**
     * @return the name
     */
    public String getName() {
      return name;
    }

    /**
     * @param name the name to set
     */
    public void setName(String name) {
      this.name = name;
    }

    /**
     * @return the value
     */
    public String getValue() {
      return value;
    }

    /**
     * @param value the value to set
     */
    public void setValue(String value) {
      this.value = value;
    }

  }

  @XmlAccessorType(XmlAccessType.FIELD)
  @XmlType(name = "")
  @XmlRootElement(name = "idws:RESULTITEM")
  public static class XmlResultItem {

    @XmlAttribute(name = "Name")
    private String name;

    @XmlAttribute(name = "Value")
    private String value;

    @XmlElement(name = "idws:RESULTITEM")
    private List<XmlResultItem> items;

    @XmlElement(name = "idws:ATTRIBUTE")
    private List<XmlResultAttribute> attributes;

    /**
     * @return the name
     */
    public String getName() {
      return name;
    }

    /**
     * @param name the name to set
     */
    public void setName(String name) {
      //there is a bug in a dependent lib, which requests this always to be non-null
      this.name = name!=null?name:"";
    }

    /**
     * @return the value
     */
    public String getValue() {
      //there is a bug in a dependent lib, which requests this always to be non-null
      return value!=null?value:"";
    }

    /**
     * @param value the value to set
     */
    public void setValue(String value) {
      this.value = value;
    }

    /**
     * @return the items
     */
    public List<XmlResultItem> getItems() {
      return items;
    }

    /**
     * @param items the items to set
     */
    public void setItems(List<XmlResultItem> items) {
      this.items = items;
    }

    /**
     * @return the attributes
     */
    public List<XmlResultAttribute> getAttributes() {
      return attributes;
    }

    /**
     * @param attributes the attributes to set
     */
    public void setAttributes(List<XmlResultAttribute> attributes) {
      this.attributes = attributes;
    }

  }

  @XmlAccessorType(XmlAccessType.FIELD)
  @XmlType(name = "")
  @XmlRootElement(name = "idws:STATUS")
  protected static class XmlStatus {

    @XmlAttribute(name = "Value")
    private Integer value;

    /**
     * @return the value
     */
    public Integer getValue() {
      return value;
    }

    /**
     * @param value the value to set
     */
    public void setValue(Integer value) {
      this.value = value;
    }

  }

  @XmlAccessorType(XmlAccessType.FIELD)
  @XmlType(name = "")
  @XmlRootElement(name = "idws:RETURN_CODE")
  protected static class XmlReturnCode {

    @XmlAttribute(name = "Value")
    private Integer value;

    /**
     * @return the value
     */
    public Integer getValue() {
      return value;
    }

    /**
     * @param value the value to set
     */
    public void setValue(Integer value) {
      this.value = value;
    }

  }

  @XmlAccessorType(XmlAccessType.FIELD)
  @XmlType(name = "")
  @XmlRootElement(name = "idws:RESULT")
  protected static class XmlResult {

    @XmlElement(name = "idws:RETURN_CODE")
    private XmlReturnCode returnCode;

    @XmlElement(name = "idws:STATUS")
    private XmlStatus status;

    @XmlElementWrapper(name = "idws:RESULT_ITEMS")
    @XmlElement(name = "idws:RESULTITEM")
    private List<XmlResultItem> resultItems;

    /**
     * @return the returnCode
     */
    public XmlReturnCode getReturnCode() {
      return returnCode;
    }

    /**
     * @param returnCode the returnCode to set
     */
    public void setReturnCode(XmlReturnCode returnCode) {
      this.returnCode = returnCode;
    }

    /**
     * @return the status
     */
    public XmlStatus getStatus() {
      return status;
    }

    /**
     * @param status the status to set
     */
    public void setStatus(XmlStatus status) {
      this.status = status;
    }

    /**
     * @return the resultItems
     */
    public List<XmlResultItem> getResultItems() {
      return resultItems;
    }

    /**
     * @param resultItems the resultItems to set
     */
    public void setResultItems(List<XmlResultItem> resultItems) {
      this.resultItems = resultItems;
    }

  }

}
