FROM public.ecr.aws/lambda/python:3.11

# 1. install dotnet + markitdown
RUN yum -y install dotnet-sdk-8.0 \
 && dotnet tool install -g markitdown

ENV PATH="$PATH:/root/.dotnet/tools"
RUN ln -s /root/.dotnet/tools/markitdown /opt/markitdown   # convenience

# 2. copy app
COPY lambda_function.py ${LAMBDA_TASK_ROOT}

CMD ["lambda_function.handler"]
