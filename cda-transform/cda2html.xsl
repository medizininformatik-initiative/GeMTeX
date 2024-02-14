<xsl:stylesheet
	xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
	xmlns:x="http://www.w3.org/2005/xpath-functions"
	xmlns:xs="http://www.w3.org/2001/XMLSchema"
	exclude-result-prefixes="xs x" 
	version="3.0">

<xsl:output method="xml" indent="yes"/>
<xsl:mode on-no-match="shallow-skip"/>

<xsl:variable name="newline"><xsl:text>
</xsl:text></xsl:variable>

<xsl:template match="/">
	<html>
		<xsl:apply-templates select="//section"/>
	</html>
</xsl:template>


<xsl:template match="content" mode="x" >
	<xsl:variable name="s">
		<xsl:value-of select="text()" />
	</xsl:variable>
	<!-- remove strange pt? at end of font tag - this makes content non-xml-->
	<xsl:value-of select="normalize-space(replace($s,'pt\?',''))" disable-output-escaping="yes"/>
</xsl:template>


<xsl:template match="section" >
	<h1>
		<xsl:value-of select="caption/."/>
	</h1>
	<xsl:apply-templates select=".//content" mode="x"/>
</xsl:template>


</xsl:stylesheet>