<xsl:stylesheet
	xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
	xmlns:x="http://www.w3.org/2005/xpath-functions"
	xmlns:xs="http://www.w3.org/2001/XMLSchema"
	exclude-result-prefixes="xs x" 
	version="3.0">

<xsl:output method="text"/>
<xsl:variable name="newline"><xsl:text>
</xsl:text></xsl:variable>

<xsl:template match="/">
	<xsl:apply-templates />
</xsl:template>

<xsl:template match="h1">
	<xsl:value-of select="concat($newline,text(),': ')"/>
</xsl:template>

<xsl:template match="table">
	<xsl:value-of select="$newline"/>
	<xsl:apply-templates/>
</xsl:template>

<xsl:template match="td[@colspan='8']">
</xsl:template>

<xsl:template match="td">
		<xsl:value-of select="normalize-space(.)"/><xsl:value-of select="' | '"/>
</xsl:template>

<xsl:template match="tr">
	<xsl:apply-templates/>
	<xsl:value-of select="$newline"/>
</xsl:template>


</xsl:stylesheet>