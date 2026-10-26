import json
import logging
from typing import Dict, Any
from .access_manager import AccessManager

logger = logging.getLogger(__name__)

logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        logger.info(
            f'Lambda invoked: {getattr(context, 'function_name', 'unknown')} '
            f'(request_id: {getattr(context, 'aws_request_id', 'unknown')})'
        )
        logger.debug(f'Event: {json.dumps(event)}')

        access_manager = AccessManager()
        report = access_manager.run()
        results = {'total': len(report.results), 'failed': len(report.failures)}

        response = {
            'statusCode': 200,
            'body': {
                'message': 'Access management workflow completed',
                'results': results,
            },
        }

        logger.info(f'Lambda completed successfully. Results: {json.dumps(results)}')
        return response

    except Exception as e:
        logger.error(f'Lambda execution failed: {str(e)}', exc_info=True)
        return {
            'statusCode': 500,
            'body': {'message': 'Lambda execution failed', 'error': str(e)},
        }
