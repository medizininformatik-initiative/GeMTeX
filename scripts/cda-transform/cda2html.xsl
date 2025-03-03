<xsl:stylesheet
	xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
	xmlns:x="http://www.w3.org/2005/xpath-functions"
	xmlns:xs="http://www.w3.org/2001/XMLSchema"
	exclude-result-prefixes="xs x" 
	version="3.0">

<xsl:output method="xml" indent="yes"/>
<xsl:mode on-no-match="shallow-skip"/>

<xsl:template match="/">
	<html>
		<xsl:apply-templates select="//content" />
	</html>
</xsl:template>

<xsl:template match="content" >
	<xsl:variable name="s" select="normalize-space(replace(replace(replace(.,'pt\?',''),'&#160;',' '),'&amp;#160;',' '))"/>
	<xsl:if test="$s != ''">
		<h1>
			<xsl:value-of select="../../caption/."/>
		</h1>
		<xsl:value-of select="$s" disable-output-escaping="yes"/>
	</xsl:if>
</xsl:template>

</xsl:stylesheet>