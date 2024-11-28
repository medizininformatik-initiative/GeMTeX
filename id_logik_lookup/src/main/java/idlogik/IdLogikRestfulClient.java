package idlogik;

import com.id.idlogik.app.IDLOGIK;
import com.id.idlogik.app.Task;
import com.id.idlogik.boundary.socket.IDLOGIKClient;
import com.id.shared.app.util.TextUtils;
import org.apache.http.*;
import org.apache.http.client.ClientProtocolException;
import org.apache.http.client.HttpClient;
import org.apache.http.client.entity.UrlEncodedFormEntity;
import org.apache.http.client.methods.HttpPost;
import org.apache.http.impl.client.HttpClientBuilder;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

public class IdLogikRestfulClient extends IDLOGIKClient {

  private static final org.slf4j.Logger logger = org.slf4j.LoggerFactory.getLogger(IdLogikRestfulClient.class);

  protected String bearerToken = "";
  private String protocol;
  private final HttpClient httpclient;

  public IdLogikRestfulClient(String protocol, String host, int port) {
    super(host, port);
    this.protocol = protocol;
    httpclient= HttpClientBuilder.create()
            .useSystemProperties()
            .build();
  }

  public String getProtocol() {
    return protocol;
  }

  @Override
  protected int internCall(Task task) {

    // erstmal pruefen, ob eine sessionID oder ein bearer token uebergeben wurde
    if (bearerToken.isEmpty() && !task.getParameter().containsKey(PARAM_SESSION_ID)) {
        // gibt es eine lokale sessionID?
        if (isAutoLogin() && TextUtils.isEmpty(getSessionID()))
          login();
        // nun muesste es eine lokale sessionID geben und die wird hinzugefuegt
        task.getParameter().put(PARAM_SESSION_ID, getSessionID());
    }

    List<NameValuePair> postParameters = new ArrayList<NameValuePair>();

    String url = IdLogikRestUtils.toPostUrl(getProtocol(), getHost(), getPort(), task, postParameters);;
    HttpPost method = new HttpPost(url);
    if (!bearerToken.isEmpty()) {
      method.setHeader(HttpHeaders.AUTHORIZATION, bearerToken);
      //For safety's sake remove any sessionId
      task.getParameter().remove(PARAM_SESSION_ID);
      logger.info("IdLogikRestfulClient using bearer token: ".concat(bearerToken));
    }

    HttpResponse response;
    try {
      method.setEntity(new UrlEncodedFormEntity(postParameters, StandardCharsets.UTF_8));
      response = httpclient.execute(method);
      if (response.getStatusLine().getStatusCode() >= 300) {
        final int statusCode = response.getStatusLine().getStatusCode();
        logger.info("ERROR " + statusCode + " for url " + url);
        switch (statusCode) {
          case 401: return IDLOGIK.IDLOGIK_ERROR_NO_ACCESS;
        }
        return IDLOGIK.IDLOGIK_ERROR_INTERNAL_IAE;
      } else {
        HttpEntity entity = response.getEntity();
        InputStream inputStream = entity.getContent();
        IdLogikRestUtils.createResultItemsFromRestCall(task, inputStream);
        inputStream.close();
        logger.info("IdLogikRestfulClient returning with " + task.getStatus());
        return task.getStatus();
      }
    } catch (ClientProtocolException e) {
      logger.error("Unexpected exception", e);
      return IDLOGIK.IDLOGIK_ERROR_INTERNAL_IAE;
    } catch (IOException e) {
      logger.error("IO exception", e);
      return IDLOGIK.IDLOGIK_ERROR_INTERNAL_IAE;
    } finally {
    }
  }

  public void setBearerToken(String bearerToken) {
    this.bearerToken = bearerToken;
  }
}
