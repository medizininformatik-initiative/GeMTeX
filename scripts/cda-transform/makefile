.PHONY: all clean distclean lib

all: arztbrief_3_anonym_in.txt arztbrief_3_anonym_in.md


arztbrief_3_anonym_in.html: arztbrief_3_anonym_in.xml lib
	java -cp  Saxon-HE-12.4.jar:xmlresolver-6.0.4.jar net.sf.saxon.Transform -xsl:cda2html.xsl -s:$< -o:$@

arztbrief_3_anonym_in.md: arztbrief_3_anonym_in.html lib
	java -cp  Saxon-HE-12.4.jar:xmlresolver-6.0.4.jar net.sf.saxon.Transform -xsl:html-to-markdown.xsl -s:$< -o:$@

arztbrief_3_anonym_in.txt: arztbrief_3_anonym_in.html lib
	java -cp  Saxon-HE-12.4.jar:xmlresolver-6.0.4.jar net.sf.saxon.Transform -xsl:html-to-text.xsl -s:$< -o:$@

clean: 
	rm -f arztbrief_3_anonym_in.html arztbrief_3_anonym_in.txt

distclean: clean
	rm -f Saxon-HE-12.4.jar xmlresolver-6.0.4.jar

lib: Saxon-HE-12.4.jar xmlresolver-6.0.4.jar

Saxon-HE-12.4.jar:
	mvn dependency:copy -Dartifact=net.sf.saxon:Saxon-HE:12.4 -DoutputDirectory=.

xmlresolver-6.0.4.jar:
	mvn dependency:copy -Dartifact=org.xmlresolver:xmlresolver:6.0.4 -DoutputDirectory=.

