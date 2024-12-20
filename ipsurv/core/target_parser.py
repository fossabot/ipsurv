import logging
import re
import urllib.parse
from abc import ABC

from ipsurv.configs import Constant
from ipsurv.core.entity import Target
from ipsurv.core.entity import ValueData
from ipsurv.core.pipeline import Pipeline
from ipsurv.requester.dns_resolver import DnsResolveRequester
from ipsurv.util.network_util import IpUtil
from ipsurv.util.sys_util import System


class TargetParser(ABC):
    def __init__(self, args, pipeline, dns_resolver):
        self.pipeline = pipeline  # type: Pipeline
        self.autodetect = args.autodetect  # type: bool
        self.dns_resolver = dns_resolver  # type: DnsResolveRequester

    def parse(self, data, original, args):
        # type: (ValueData, str, object) -> Target

        target = self._parse_target(data, original, args)

        identify = self.pipeline.pre_target_identify(data, target)

        if identify:
            self._identify_target(data, target, args)

        if target.status != Constant.STATUS_EXIST:
            target.identifier = target.status

        self._assign_data_target(data, target)

        if System.is_logging():
            logging.log(logging.DEBUG, 'TARGET_RAW:' + target.raw)
            logging.log(logging.INFO, 'TARGET_IDENTIFIER:' + str(target.identifier))

            System.output_data('TARGET_DATA', target.get_values())

        return target

    def _parse_target(self, data, original, args):
        # type: (ValueData, str, object) -> Target

        if self.autodetect:
            raw = self._detect_target_raw(original, args)
        else:
            raw = original

        return self._create_target(raw.strip())

    def _identify_target(self, data, target, args):
        # type: (ValueData, Target, object) -> None

        if target.raw:
            identified = self._identify_target_ip(data, target, args)

            if identified:
                target.status = Constant.STATUS_EXIST
        else:
            target.status = Constant.STATUS_EMPTY

        data.set('ip', target.ip)
        data.set('ip_int', target.identifier_int)
        data.set('port', target.port)

        logging.info('IP:' + str(target.ip))
        logging.info('FQDN:' + str(target.fqdn))
        logging.info('PORT:' + str(target.port))

    def _identify_target_ip(self, data, target, args):
        # type: (ValueData, Target, object) -> bool
        url = self._find_url(target.raw)

        identified = False

        if url:
            target.url = url

            parsed = urllib.parse.urlparse(url)
            netloc = parsed.netloc
        else:
            netloc = target.raw

        (fqdn_ip, port) = self._split_port(netloc)

        target.port = port

        if fqdn_ip:
            ip = self._find_ip(fqdn_ip)

            if not ip:
                fqdn = self._find_fqdn(fqdn_ip)

                target.fqdn = fqdn

                if fqdn:
                    if args.resolve:
                        try:
                            ip = self.dns_resolver.resolve_ip(fqdn)
                        except Exception:
                            target.status = Constant.STATUS_RESOLVE_FAIL
                else:
                    target.status = Constant.STATUS_ILLEGAL_FORMAT

            target.identifier = target.ip = ip

            if ip:
                target.identifier_int = IpUtil.get_ip_int(target.identifier)
                identified = True

        return identified

    def _assign_data_target(self, data, target):
        # type: (ValueData, Target) -> None
        data.set('identifier', target.identifier)
        data.set('identifier_int', target.identifier_int)

        data.set('target', target)

    def _detect_target_raw(self, original, args):
        rows = re.split(args.fixed_delimiter, original)

        for row in rows:
            if self._find_url(row) or self._find_fqdn(row) or self._find_ip(row):
                return row

        return ''

    def _split_port(self, v):
        vals = v.split(':')
        port = None

        if len(vals) == 2:
            fqdn_ip = vals[0]

            try:
                port = int(vals[1])
            except Exception:
                pass
        else:
            fqdn_ip = vals[0]

        return fqdn_ip, port

    def _find_url(self, v):
        m = re.search(r'(https?:\/\/|\/\/)[a-z0-9][a-z0-9.\-/?=&_%!+:]+', v, flags=re.IGNORECASE)

        return m.group() if m is not None else None

    def _find_fqdn(self, v):
        m = re.search(r'([a-z0-9\-]{1,128}(?<!\-)\.)+[a-z0-9]{2,}', v, flags=re.IGNORECASE)

        return m.group() if m is not None else None

    def _find_ip(self, v):
        m = re.search(r'[\d]{1,3}\.[\d]{1,3}\.[\d]{1,3}\.[\d]{1,3}', v)

        return m.group() if m is not None else None

    def _create_target(self, raw):
        return Target(raw.strip())
