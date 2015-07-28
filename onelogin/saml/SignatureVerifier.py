import os
import subprocess
import platform
import tempfile
import logging

from lxml import etree

from onelogin.saml.Utils import calculate_x509_fingerprint, format_cert

log = logging.getLogger(__name__)


class SignatureVerifierError(Exception):
    """There was a problem validating the response"""
    def __init__(self, msg):
        self._msg = msg

    def __str__(self):
        return '%s: %s' % (self.__doc__, self._msg)


def _parse_stderr(output, procreturncode):
    #output = proc.stderr.read()
    for line in output.split('\n'):
        line = line.strip()
        if line == 'OK':
            return True
        elif line == 'FAIL':
            [log.info('XMLSec: %s' % line)
             for line in output.split('\n')
             if line
             ]
            return False

    # If neither success nor failure
    if procreturncode is not 0:
        msg = ('XMLSec returned error code ' + str(procreturncode) + '. Please check your '
               + 'certficate.' + 'sig=signature' + '&doc_str=doc_str' + '&op=' + output + '&err=' + error +  '&cmd=' + " ".join(cmds)
               )
        raise SignatureVerifierError(msg)

    # Should not happen
    raise SignatureVerifierError(
        ('XMLSec exited with code 0 but did not return OK when verifying the '
         + ' SAML response.' + '&op=' + output + '&err=' + error +  '&cmd=' + cmds
         )
    )


def _get_xmlsec_bin(_platform=None):
    if _platform is None:
        _platform = platform

    xmlsec_bin = 'xmlsec1'
    if _platform.system() == 'Windows':
        xmlsec_bin = 'xmlsec.exe'

    return xmlsec_bin


def verify(document, signature, _etree=None, _tempfile=None, _subprocess=None,
           _os=None):
    """
    Verify that signature contained in the samlp:Response is valid when checked
    against the provided signature. Return True if valid, otherwise False
    Arguments:
    document -- lxml.etree.XML object containing the samlp:Response
    signature -- The fingerprint to check the samlp:Response against
    """
    if _etree is None:
        _etree = etree
    if _tempfile is None:
        _tempfile = tempfile
    if _subprocess is None:
        _subprocess = subprocess
    if _os is None:
        _os = os

    signatureNodes = document.xpath("//ds:Signature", namespaces={'ds': 'http://www.w3.org/2000/09/xmldsig#'})

    parent_id_container = 'urn:oasis:names:tc:SAML:2.0:assertion:Assertion'
    if signatureNodes and signatureNodes[0].getparent().tag == '{urn:oasis:names:tc:SAML:2.0:protocol}Response':
        parent_id_container = 'urn:oasis:names:tc:SAML:2.0:protocol:Response'

    certificateNodes = document.xpath("//ds:X509Certificate", namespaces={'ds': 'http://www.w3.org/2000/09/xmldsig#'})

    if not certificateNodes or calculate_x509_fingerprint(certificateNodes[0].text) != signature:
        return False
    else:
        # use the x509 cert instead of fingerprint required by xmlsec
        signature = format_cert(certificateNodes[0].text)

    xmlsec_bin = _get_xmlsec_bin()

    verified = False
    cert_filename = None
    xml_filename = None
    # Windows hack: Without the delete=False parameter in NamedTemporaryFile
    # xmlsec.exe will get an IO Permission Denied error.
    try:
        with _tempfile.NamedTemporaryFile(delete=False) as xml_fp:
            doc_str = _etree.tostring(document)
            xml_fp.write(doc_str)
            xml_fp.seek(0)
            with _tempfile.NamedTemporaryFile(delete=False) as cert_fp:
                cert_fp.write(signature)
                cert_fp.seek(0)

                cert_filename = cert_fp.name
                xml_filename = xml_fp.name

                # We cannot use xmlsec python bindings to verify here because
                # that would require a call to libxml2.xmlAddID. The libxml2
                # python bindings do not yet provide this function.
                # http://www.aleksey.com/xmlsec/faq.html Section 3.2
                cmds = "xmlsec1 --verify --pubkey-cert-pem " + cert_filename + " --id-attr:ID urn:oasis:names:tc:SAML:2.0:assertion:Assertion " + xml_filename
                proc = _subprocess.Popen(
                    cmds, shell=True,
                    stderr=_subprocess.PIPE,
                    stdout=_subprocess.PIPE                  
                )    
                out, err = proc.communicate()            
                # proc.wait()
                verified = _parse_stderr(err, proc.returncode)
                
    finally:
        if cert_filename is not None:
            _os.remove(cert_filename)
        if xml_filename is not None:
            _os.remove(xml_filename)

    return verified
    return True
